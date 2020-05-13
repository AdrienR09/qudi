# -*- coding: utf-8 -*-
"""
This file contains the Qudi logic class that captures and processes photoluminescence
spectra and the spot image.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

from qtpy import QtCore
from collections import OrderedDict
import numpy as np

from core.connector import Connector
from core.statusvariable import StatusVar
from core.util.mutex import Mutex
from core.util.network import netobtain
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from logic.save_logic import SaveLogic

import math as mt


class DataAnalysisLogic(GenericLogic):

    ##############################################################################
    #                            Initialization functions
    ##############################################################################


    _file_path = StatusVar("file_path", None)
    if _file_path == None:
        _file_path = ConfigOption("file_path", missing='warn')

    _data = StatusVar("spim_matrix", np.empty((2,2,2)))
    _axis_range = StatusVar("axis_range", [(0,10e-4),(0,10e-4),(0,10e-4)])
    _axis_name = StatusVar("axis_name", ["X axis", "Y axis", "Wavelength"])
    _axis_unit = StatusVar("axis_unit", ["m", "m", "nm"])
    _values_name = StatusVar("values_name", "counts")
    _values_unit = StatusVar("values_unit", "/s")


    def __init__(self, **kwargs):
        """ Create SpectrumLogic object with connectors and status variables loaded.

          @param dict kwargs: optional parameters
        """
        super().__init__(**kwargs)

    def on_activate(self):

        with open(self._file_path, mode='r', encoding='latin-1') as file:
            self._data = file.read()


    def define_axis(self, axis_name, axis_range):
        """ Function defining the principe data_axis
        """
        if not len(axis_name) == self._dim:
            self.log.warning("")
        self._axis_range = axis_range
        self._axis_name = axis_name

    def planar_slicer(self, normal_vector, offset_vector):
        """This function slice a data cube (with 3 dimensions) with an affine plane with parameters its normal vector
        define in 3D space (x, y, z) and an offset value corresponding of the z value at x=0 and y=0. This slicing
        is not periodic, if z value in the plane become negative the values are removed. A 2D data array corresponding
        to the slicing is returned.

                Z axis    Y axis
                *  ......*...........
        offset--*.......*...........
        value   *  ....*...........
                *    .*...........
                *    * ..........
                *   *    .......
                *  *       ....
                * *          .
                * * * * * * * * * * * * * * * * * * X axis
        """
        data_shape = self._data.shape
        v1, v2, v3 = normal_vector
        x0, y0, z0 = offset_vector
        if v3 == 0:
            x_pos = np.arange(data_shape[0]) - x0
            y_pos = -v1 / v2 * x_pos + y0
            sliced_data = np.array(
                [self._data[i, int(y_pos[i]), :] for i in x_pos if data_shape[1] > y_pos[i] >= 0])
            sliced_data = np.transpose(sliced_data, (1, 0))
        else:
            x_pos = np.arange(data_shape[0]) - x0
            y_pos = np.arange(data_shape[1]) - y0
            X_pos, Y_pos = np.meshgrid(x_pos, y_pos)
            Z_pos = -v1 / v3 * X_pos - v2 / v3 * Y_pos + z0
            Z_pos = Z_pos.T
            sliced_data = np.array(
                [[self._data[i, j, int(Z_pos[i, j])] for i in x_pos if data_shape[2] > Z_pos[i, j] >= 0
                  ] for j in y_pos])
        return sliced_data

    def area_slicer(self, width, normal_vector, offset_vector):
        data_shape = self._data.shape
        v1, v2, v3 = normal_vector
        x0, y0, z0 = offset_vector
        if v3 == 0:
            x_pos = np.arange(data_shape[0]) - x0
            y_min = -v1 / v2 * x_pos + y0 - width/2
            y_max = -v1 / v2 * x_pos + y0 + width/2
            sliced_data = np.array(
                [[self._data[i, j, :] for j in range(int(y_min[i]), int(y_max[i])) if data_shape[1] > j >= 0]
                 for i in x_pos])
            sliced_data = np.transpose(sliced_data, (2, 0, 1))
        else:
            x_pos = np.arange(data_shape[0]) - x0
            y_pos = np.arange(data_shape[1]) - y0
            X_pos, Y_pos = np.meshgrid(x_pos, y_pos)
            Z_min = -v1 / v3 * X_pos - v2 / v3 * Y_pos + z0 - width/2
            Z_max = -v1 / v3 * X_pos - v2 / v3 * Y_pos + z0 + width/2
            sliced_data = np.array(
                [[[self._data[i, j, k] for k in range(int(Z_min[i, j]),int(Z_max[i, j])) if data_shape[2] > k >= 0]
                  for i in x_pos ] for j in y_pos])
            sliced_data = np.transpose(sliced_data, (2, 0, 1))
        return sliced_data

def area_slicer(data, width, normal_vector, offset_vector):
    data_shape = data.shape
    v1, v2, v3 = normal_vector
    x0, y0, z0 = offset_vector
    if v3 == 0:
        x_pos = np.arange(data_shape[0]) - x0
        y_min = -v1 / v2 * x_pos + y0 + width/2
        y_max = -v1 / v2 * x_pos + y0 - width/2
        sliced_data = np.array(
            [[data[i, j, :] for j in range(int(y_min[i]), int(y_max[i])) if data_shape[1] > j >= 0]
             for i in x_pos])
    else:
        x_pos = np.arange(data_shape[0]) - x0
        y_pos = np.arange(data_shape[1]) - y0
        X_pos, Y_pos = np.meshgrid(x_pos, y_pos)
        Z_min = -v1 / v3 * X_pos - v2 / v3 * Y_pos + z0 - width/2
        Z_max = -v1 / v3 * X_pos - v2 / v3 * Y_pos + z0 + width/2
        sliced_data = np.array(
            [[[data[i, j, k] for k in range(int(Z_min[i, j]),int(Z_max[i, j])) if data_shape[2] > k >= 0]
              for i in x_pos ] for j in y_pos])
        sliced_data = np.transpose(sliced_data, (2, 0, 1))
    return sliced_data