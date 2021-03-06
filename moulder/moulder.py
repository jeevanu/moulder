from __future__ import division, absolute_import
from future.builtins import super, zip

import numpy
from matplotlib import pyplot, patches
from matplotlib.lines import Line2D
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from PyQt5.QtCore import Qt, pyqtSignal

from fatiando import utils
from fatiando.gravmag import talwani
from fatiando.mesher import Polygon

LINE_ARGS = dict(
    linewidth=2, linestyle='-', color='k', marker='o',
    markerfacecolor='k', markersize=5, animated=False, alpha=0.6)


class Moulder(FigureCanvasQTAgg):

    # The tolerance range for mouse clicks on vertices. In pixels.
    epsilon = 5
    # App instructions printed in the figure suptitle
    instructions = ' | '.join([
        'n: New polygon', 'd: delete', 'click: select/move', 'a: add vertex',
        'r: reset view', 'esc: cancel'])

    # Signal when selected polygon changes
    polygon_selected = pyqtSignal(float)
    drawing_mode = pyqtSignal(bool)
    add_vertex_mode = pyqtSignal(bool)

    def __init__(self, parent, x, z, min_depth, max_depth,
                 density_range=[-2000, 2000], width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.dataax, self.modelax = self.fig.subplots(2, 1, sharex=True)
        super().__init__(self.fig)
        self.setParent(parent)

        self.min_depth, self.max_depth = min_depth, max_depth
        self._x, self._z = x, z
        self.density_range = density_range
        self._predicted = numpy.zeros_like(x)
        self._data = None
        self.predicted_line = None
        self.cmap = pyplot.cm.RdBu_r
        self.canvas = self.fig.canvas

        self.polygons = []
        self.lines = []
        self.densities = []

        # Initialize density and error values
        self._density = 0
        self._error = 0

        # Data min and max (only for first implementations)
        # They will be determined when data is imported
        self.dmin, self.dmax = 0, 0

        self._figure_setup()
        self._init_markers()
        self._connect()

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, new_value):
        self._x = numpy.asarray(new_value)

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, new_value):
        self._z = numpy.asarray(new_value)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, new_data):
        self._data = new_data

    @property
    def density(self):
        return self._density

    @density.setter
    def density(self, value):
        """
        Callback when density slider is edited
        """
        self._density = value
        if self._ipoly is not None:
            self.densities[self._ipoly] = value
            self.polygons[self._ipoly].set_color(self._density2color(value))
            # self._update_data()
            self._update_data_plot()
            self.canvas.draw()

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, value):
        """
        Callback when error slider is edited
        """
        self._error = value
        self._update_data_plot()

    @property
    def predicted(self):
        self._predicted = talwani.gz(self.x, self.z, self.model)
        if self.error > 0:
            self._predicted = utils.contaminate(self._predicted, self.error)
        return self._predicted

    @property
    def model(self):
        """
        The polygon model drawn as :class:`fatiando.mesher.Polygon` objects.
        """
        m = [Polygon(p.xy, {'density': d}, force_clockwise=True)
             for p, d in zip(self.polygons, self.densities)]
        return m

    def add_vertex(self):
        self._add_vertex = not self._add_vertex
        # self.add_vertex_mode.emit(True)

    def new_polygon(self):
        self._ivert = None
        self._ipoly = None
        for line, poly in zip(self.lines, self.polygons):
            poly.set_animated(False)
            line.set_animated(False)
            line.set_color([0, 0, 0, 0])
        self.canvas.draw()
        self.background = self.canvas.copy_from_bbox(self.modelax.bbox)
        self._drawing = True
        self.drawing_mode.emit(self._drawing)
        self._xy = []
        self._drawing_plot = Line2D([], [], **LINE_ARGS)
        self._drawing_plot.set_animated(True)
        self.modelax.add_line(self._drawing_plot)
        self.dataax.set_title(' | '.join([
            'left click: set vertice', 'right click: finish',
            'esc: cancel']))
        self.canvas.draw()

    def delete_polygon(self):
        if self._drawing and self._xy:
            self._xy.pop()
            if self._xy:
                self._drawing_plot.set_data(list(zip(*self._xy)))
            else:
                self._drawing_plot.set_data([], [])
            self.canvas.restore_region(self.background)
            self.modelax.draw_artist(self._drawing_plot)
            self.canvas.blit(self.modelax.bbox)
        elif self._ivert is not None:
            poly = self.polygons[self._ipoly]
            line = self.lines[self._ipoly]
            if len(poly.xy) > 4:
                verts = numpy.atleast_1d(self._ivert)
                poly.xy = numpy.array([xy for i, xy in enumerate(poly.xy)
                                       if i not in verts])
                line.set_data(list(zip(*poly.xy)))
                # self._update_data()
                self._update_data_plot()
                self.canvas.restore_region(self.background)
                self.modelax.draw_artist(poly)
                self.modelax.draw_artist(line)
                self.canvas.blit(self.modelax.bbox)
                self._ivert = None
        elif self._ipoly is not None:
            self.polygons[self._ipoly].remove()
            self.lines[self._ipoly].remove()
            self.polygons.pop(self._ipoly)
            self.lines.pop(self._ipoly)
            self.densities.pop(self._ipoly)
            self._ipoly = None
            self.canvas.draw()
            # self._update_data()
            self._update_data_plot()
            self.add_vertex_mode.emit(False)

    def cancel_drawing(self):
        if self._add_vertex:
            self._add_vertex = False
            self.add_vertex_mode.emit(False)
        else:
            self.dataax.set_title(self.instructions)
            self._drawing = False
            self.drawing_mode.emit(self._drawing)
            self._xy = []
            if self._drawing_plot is not None:
                self._drawing_plot.remove()
                self._drawing_plot = None
            for line, poly in zip(self.lines, self.polygons):
                poly.set_animated(False)
                line.set_animated(False)
                line.set_color([0, 0, 0, 0])
        self.canvas.draw()

    def set_meassurement_points(self, x, z):
        self.x = x
        self.z = z
        self._figure_setup()
        self._update_data_plot()

    def _figure_setup(self):
        self.dataax.set_title(self.instructions)
        self.dataax.set_ylabel("Gravity Anomaly [mGal]")
        self.dataax.set_ylim((-200, 200))
        self.dataax.grid(True)
        self.modelax.set_xlabel("x [m]")
        self.modelax.set_ylabel("z [m]")
        self.modelax.set_xlim(self.x.min(), self.x.max())
        self.modelax.set_ylim(self.min_depth, self.max_depth)
        self.modelax.grid(True)
        self.modelax.invert_yaxis()
        if self.predicted_line is not None:
            self.predicted_line.remove()
        self.predicted_line, = self.dataax.plot(self.x, self.predicted, '-r')
        self.canvas.draw()

    def _init_markers(self):
        self._ivert = None
        self._ipoly = None
        self._lastevent = None
        self._drawing = False
        self.drawing_mode.emit(self._drawing)
        self._add_vertex = False
        self._xy = []
        self._drawing_plot = None
        self.background = None

    def _connect(self):
        """
        Connect the matplotlib events to their callback methods.
        """
        # Make the proper callback connections
        self.canvas.mpl_connect('button_press_event',
                                self._button_press_callback)
        self.canvas.mpl_connect('button_release_event',
                                self._button_release_callback)
        self.canvas.mpl_connect('motion_notify_event',
                                self._mouse_move_callback)

    def _density2color(self, density):
        """
        Map density values to colors using the given *cmap* attribute.

        Parameters:

        * density : 1d-array
            The density values of the model polygons

        Returns

        * colors : 1d-array
            The colors mapped to each density value (returned by a matplotlib
            colormap object.

        """
        dmin, dmax = self.density_range
        return self.cmap((density - dmin)/(dmax - dmin))

    def _make_polygon(self, vertices, density):
        """
        Create a polygon for drawing.

        Polygons are matplitlib.patches.Polygon objects for the fill and
        matplotlib.lines.Line2D for the contour.

        Parameters:

        * vertices : list of [x, z]
            List of the [x, z]  coordinate pairs of each vertex of the polygon
        * density : float
            The density of the polygon (used to set the color)

        Returns:

        * polygon, line
            The matplotlib Polygon and Line2D objects

        """
        poly = patches.Polygon(vertices, animated=False, alpha=0.9,
                               color=self._density2color(density))
        x, y = list(zip(*poly.xy))
        line = Line2D(x, y, **LINE_ARGS)
        return poly, line

    def _update_data_plot(self):
        """
        Update the predicted data plot in the *dataax*.

        Adjusts the xlim of the axes to fit the data.
        """
        predicted = self.predicted
        self.predicted_line.set_ydata(predicted)
        vmin = 1.2*min(predicted.min(), self.dmin)
        vmax = 1.2*max(predicted.max(), self.dmax)
        self.dataax.set_ylim(vmin, vmax)
        self.dataax.grid(True)
        self.canvas.draw()

    def _get_polygon_vertice_id(self, event):
        """
        Find out which vertex of which polygon the event happened in.

        If the click was inside a polygon (not on a vertex), identify that
        polygon.

        Returns:

        * p, v : int, int
            p: the index of the polygon the event happened in or None if
            outside all polygons.
            v: the index of the polygon vertex that was clicked or None if the
            click was not on a vertex.

        """
        distances = []
        indices = []
        for poly in self.polygons:
            x, y = poly.get_transform().transform(poly.xy).T
            d = numpy.sqrt((x - event.x)**2 + (y - event.y)**2)
            distances.append(d.min())
            indices.append(numpy.argmin(d))
        p = numpy.argmin(distances)
        if distances[p] >= self.epsilon:
            # Check if the event was inside a polygon
            x, y = event.x, event.y
            p, v = None, None
            for i, poly in enumerate(self.polygons):
                if poly.contains_point([x, y]):
                    p = i
                    break
        else:
            v = indices[p]
            last = len(self.polygons[p].xy) - 1
            if v == 0 or v == last:
                v = [0, last]
        return p, v

    def _add_new_vertex(self, event):
        """
        Add new vertex to polygon
        """
        vertices = self.polygons[self._ipoly].get_xy()
        x, y = vertices[:, 0], vertices[:, 1]
        # Compute the angle between the vectors to each pair of
        # vertices corresponding to each line segment of the polygon
        x1, y1 = x[:-1], y[:-1]
        x2, y2 = numpy.roll(x1, -1), numpy.roll(y1, -1)
        u = numpy.vstack((x1 - event.xdata, y1 - event.ydata)).T
        v = numpy.vstack((x2 - event.xdata, y2 - event.ydata)).T
        angle = numpy.arccos(numpy.sum(u*v, 1) /
                             numpy.sqrt(numpy.sum(u**2, 1)) /
                             numpy.sqrt(numpy.sum(v**2, 1)))
        position = angle.argmax() + 1
        x = numpy.hstack((x[:position], event.xdata, x[position:]))
        y = numpy.hstack((y[:position], event.ydata, y[position:]))
        new_vertices = numpy.vstack((x, y)).T
        return new_vertices

    def _button_press_callback(self, event):
        """
        What actions to perform when a mouse button is clicked
        """
        if event.inaxes != self.modelax:
            return
        if event.button == 1 and not self._drawing and self.polygons:
            self._lastevent = event
            if not self._add_vertex:
                for line, poly in zip(self.lines, self.polygons):
                    poly.set_animated(False)
                    line.set_animated(False)
                    line.set_color([0, 0, 0, 0])
                self.canvas.draw()
                # Find out if a click happened on a vertice
                # and which vertice of which polygon
                self._ipoly, self._ivert = self._get_polygon_vertice_id(event)
                if self._ipoly is not None:
                    # Emit signal: selected polygon changed (sends density)
                    self.polygon_selected.emit(self.densities[self._ipoly])
                    # self.density_slider.set_val(self.densities[self._ipoly])
                    self.polygons[self._ipoly].set_animated(True)
                    self.lines[self._ipoly].set_animated(True)
                    self.lines[self._ipoly].set_color([0, 1, 0, 0])
                    self.canvas.draw()
                    self.background = self.canvas.copy_from_bbox(
                        self.modelax.bbox)
                    self.modelax.draw_artist(self.polygons[self._ipoly])
                    self.modelax.draw_artist(self.lines[self._ipoly])
                    self.canvas.blit(self.modelax.bbox)
            else:
                # If a polygon is selected, we will add a new vertex by
                # removing the polygon and inserting a new one with the extra
                # vertex.
                if self._ipoly is not None:
                    vertices = self._add_new_vertex(event)
                    density = self.densities[self._ipoly]
                    polygon, line = self._make_polygon(vertices, density)
                    self.polygons[self._ipoly].remove()
                    self.lines[self._ipoly].remove()
                    self.polygons.pop(self._ipoly)
                    self.lines.pop(self._ipoly)
                    self.polygons.insert(self._ipoly, polygon)
                    self.lines.insert(self._ipoly, line)
                    self.modelax.add_patch(polygon)
                    self.modelax.add_line(line)
                    self.lines[self._ipoly].set_color([0, 1, 0, 0])
                    self.canvas.draw()
                    # self._update_data()
                    self._update_data_plot()
        elif self._drawing:
            if event.button == 1:
                self._xy.append([event.xdata, event.ydata])
                self._drawing_plot.set_data(list(zip(*self._xy)))
                self.canvas.restore_region(self.background)
                self.modelax.draw_artist(self._drawing_plot)
                self.canvas.blit(self.modelax.bbox)
            elif event.button == 3:
                if len(self._xy) >= 3:
                    poly, line = self._make_polygon(self._xy, self.density)
                    self.polygons.append(poly)
                    self.lines.append(line)
                    self.densities.append(self.density)
                    self.modelax.add_patch(poly)
                    self.modelax.add_line(line)
                    self._drawing_plot.remove()
                    self._drawing_plot = None
                    self._xy = None
                    self._drawing = False
                    self.drawing_mode.emit(self._drawing)
                    self._ipoly = len(self.polygons) - 1
                    self.lines[self._ipoly].set_color([0, 1, 0, 0])
                    self.dataax.set_title(self.instructions)
                    self.canvas.draw()
                    # self._update_data()
                    self._update_data_plot()

    def _button_release_callback(self, event):
        """
        Reset place markers on mouse button release
        """
        if event.inaxes != self.modelax:
            return
        if event.button != 1:
            return
        if self._add_vertex:
            self._add_vertex = False
            self.add_vertex_mode.emit(False)
        if self._ivert is None and self._ipoly is None:
            return
        self.background = None
        for line, poly in zip(self.lines, self.polygons):
            poly.set_animated(False)
            line.set_animated(False)
        self.canvas.draw()
        self._ivert = None
        # self._ipoly is only released when clicking outside
        # the polygons
        self._lastevent = None
        # self._update_data()
        self._update_data_plot()

    def _mouse_move_callback(self, event):
        """
        Handle things when the mouse move.
        """
        if event.inaxes != self.modelax:
            return
        if event.button != 1:
            return
        if self._ivert is None and self._ipoly is None:
            return
        if self._add_vertex:
            return
        x, y = event.xdata, event.ydata
        p = self._ipoly
        v = self._ivert
        if self._ivert is not None:
            self.polygons[p].xy[v] = x, y
        else:
            dx = x - self._lastevent.xdata
            dy = y - self._lastevent.ydata
            self.polygons[p].xy[:, 0] += dx
            self.polygons[p].xy[:, 1] += dy
        self.lines[p].set_data(list(zip(*self.polygons[p].xy)))
        self._lastevent = event
        self.canvas.restore_region(self.background)
        self.modelax.draw_artist(self.polygons[p])
        self.modelax.draw_artist(self.lines[p])
        self.canvas.blit(self.modelax.bbox)

    def keyPressEvent(self, event):
        """
        What to do when a key is pressed on the keyboard.
        """
        if event.key() == Qt.Key_D:
            self.delete_polygon()
        elif event.key() == Qt.Key_N:
            self.new_polygon()
        elif event.key() == Qt.Key_Escape:
            self.cancel_drawing()
        elif event.key() == Qt.Key_R:
            self.modelax.set_xlim(self.x.min(), self.x.max())
            self.modelax.set_ylim(self.max_depth, self.min_depth)
            self._update_data_plot()
        elif event.key() == Qt.Key_A:
            self.add_vertex()
