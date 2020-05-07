# -*- coding: utf-8 -*-
"""
This module interface Shamrock spectrometer from Andor.

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
na=not applicable
"""
import numpy as np
import ctypes as ct

from core.module import Base
from core.configoption import ConfigOption

from interface.spectrometer_complete_interface import SpectrometerInterface
from interface.spectrometer_complete_interface import Grating, PortType, Port, Constraints


INPUT_CODE = 1
OUTPUT_CODE = 2

FRONT_CODE = 0
SIDE_CODE = 1


class Main(Base, SpectrometerInterface):
    """ Hardware module that interface a dummy grating spectrometer
    """

    _slit_range = ConfigOption('slit_range', [10e-6, 2500e-6]) # Define the slit width limits for slit width controller

    # Declarations of attributes to make Pycharm happy
    def __init__(self):
        self._constraints = None
        self._dll = None
        self._shutter_status = None
        self._device_id = None

    ##############################################################################
    #                            Basic functions
    ##############################################################################
    def on_activate(self):
        """ Activate module """

        self._constraints = self._build_constraints()

        self._grating_index = 0
        self._center_wavelength = 200e-9
        self._input_port = 0
        self._output_port = 0
        self._slit_width = 100e-6
        self._number_of_gratings = 3
        self._number_of_pixels = 2048
        self._pixel_width = 1e-4
        self._detector_offset = 0

    def on_deactivate(self):
        """ De-initialisation performed during deactivation of the module. """
        pass

    def _build_constraints(self):
        """ Internal method that build the constraints once at initialisation

         This makes multiple call to the DLL, so it will be called only once by on_activate
         """
        constraints = Constraints()

        optical_param = self._get_optical_parameters()
        constraints.focal_length = optical_param['focal_length']
        constraints.angular_deviation = optical_param['angular_deviation']
        constraints.focal_tilt = optical_param['focal_tilt']

        number_of_gratings = self._get_number_gratings()
        for i in range(number_of_gratings):
            grating_info = self._get_grating_info(i)
            grating = Grating()
            grating.ruling = grating_info['ruling']
            grating.blaze = grating_info['blaze']
            grating.wavelength_max = self._get_wavelength_limit(i)[1]
            constraints.gratings.append(grating)

        # Add the ports one by one
        input_port_front = Port(PortType.INPUT_FRONT)
        input_port_front.is_motorized = self._auto_slit_is_present('input', 'front')
        constraints.ports.append(input_port_front)

        if self.flipper_mirror_is_present('input'):
            input_port_side = Port(PortType.INPUT_SIDE)
            input_port_side.is_motorized = self._auto_slit_is_present('input', 'side')
            constraints.ports.append(input_port_side)

        output_port_front = Port(PortType.OUTPUT_FRONT)
        output_port_front.is_motorized = self._auto_slit_is_present('output', 'front')
        constraints.ports.append(output_port_front)

        if self.flipper_mirror_is_present('output'):
            output_port_side = Port(PortType.OUTPUT_SIDE)
            output_port_side.is_motorized = self._auto_slit_is_present('output', 'side')
            constraints.ports.append(output_port_side)

        for port in constraints.ports:
            port.constraints.min = self.SLIT_MIN_WIDTH
            port.constraints.max = self.SLIT_MAX_WIDTH

        return constraints

    ##############################################################################
    #                            Interface functions
    ##############################################################################
    def get_constraints(self):
        """ Returns all the fixed parameters of the hardware which can be used by the logic.

        @return (Constraints): An object of class Constraints containing all fixed parameters of the hardware
        """
        return self._constraints

    def get_grating_index(self):
        """ Returns the current grating index

        @return (int): Current grating index
        """
        return self._grating_index

    def set_grating_index(self, value):
        """ Sets the grating by index

        @param (int) value: grating index
        """
        self._grating_index = value

    def get_wavelength(self):
        """ Returns the current central wavelength in meter

        @return (float): current central wavelength (meter)
        """
        return self._center_wavelength

    def set_wavelength(self, value):
        """ Sets the new central wavelength in meter

        @params (float) value: The new central wavelength (meter)
        """
        grating_index = self.get_grating_index()
        maxi = self.get_constraints().gratings[grating_index].wavelength_max
        if 0 <= value <= maxi:
            self._center_wavelength = value
        else:
            self.log.error('The wavelength {} is not in the range {}, {}'.format(value*1e9, 0, maxi*1e9))

    def get_input_port(self):
        """ Returns the current input port

        @return (PortType): current port side
        """
        return self._input_port

    def set_input_port(self, value):
        """ Set the current input port

        @param (PortType) value: The port side to set
        """
        if value in [0,1]:
            self._input_port = value
        else:
            self.log.warning("The input port value is not correct : should be 0 or 1 ")

    def get_output_port(self):
        """ Returns the current output port

        @return (PortType): current port side
        """
        return self._output_port

    def set_output_port(self, value):
        """ Set the current output port

        @param (PortType) value: The port side to set
        """
        if value in [0, 1]:
            self._output_port = value
        else:
            self.log.warning("The input port value is not correct : should be 0 or 1 ")

    def get_slit_width(self, port_type):
        """ Getter for the current slit width in meter on a given port

        @param (PortType) port_type: The port to inquire

        @return (float): input slit width (in meter)
        """
        return self._slit_width

    def set_slit_width(self, port_type, value):
        """ Setter for the input slit width in meter

        @param (PortType) port_type: The port to set
        @param (float) value: input slit width (in meter)
        """
        if self.SLIT_MIN_WIDTH <= value <= self.SLIT_MAX_WIDTH:
            self._slit_width = value
        else:
            self.log.error('Slit with ({} um) out of range.'.format(value*1e6))

