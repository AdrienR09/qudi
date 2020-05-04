# -*- coding: utf-8 -*-

"""
This hardware module implement the camera spectrometer interface to use an Andor Camera.
It use a dll to interface with instruments via USB (only available physical interface)
This module does aim at replacing Solis.

---

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

from enum import Enum
import numpy as np
import ctypes as ct

from core.module import Base
from core.configoption import ConfigOption

from interface.spectroscopy_camera_interface import SpectroscopyCameraInterface
from interface.spectroscopy_camera_interface import ReadMode, Constraints, ImageAdvancedParameters


# Bellow are the classes used by Andor dll. They are not par of Qudi interfaces
class ReadModeDLL(Enum):
    """ Class defining the possible read mode supported by Andor DLL

    This read mode is different from the class of the interface, be careful!
    Only FVB, RANDOM_TRACK and IMAGE are used by this module.
     """
    FVB = 0
    MULTI_TRACK = 1
    RANDOM_TRACK = 2
    SINGLE_TRACK = 3
    IMAGE = 4


class AcquisitionMode(Enum):
    """ Class defining the possible acquisition mode supported by Andor DLL

     Only SINGLE_SCAN is used by this module.
     """
    SINGLE_SCAN = 1
    ACCUMULATE = 2
    KINETICS = 3
    FAST_KINETICS = 4
    RUN_TILL_ABORT = 5


class TriggerMode(Enum):
    """ Class defining the possible trigger mode supported by Andor DLL """
    INTERNAL = 0
    EXTERNAL = 1
    EXTERNAL_START = 6
    EXTERNAL_EXPOSURE = 7
    SOFTWARE_TRIGGER = 10
    EXTERNAL_CHARGE_SHIFTING = 12


class ShutterMode(Enum):
    """ Class defining the possible shutter mode supported by Andor DLL """
    AUTO = 0
    OPEN = 1
    CLOSE = 2


OK_CODE = 20002  # Status code associated with DRV_SUCCESS

# Error codes and strings defines by the DLL
ERROR_DICT = {
    20001: "DRV_ERROR_CODES",
    20002: "DRV_SUCCESS",
    20003: "DRV_VX_NOT_INSTALLED",
    20006: "DRV_ERROR_FILE_LOAD",
    20007: "DRV_ERROR_VXD_INIT",
    20010: "DRV_ERROR_PAGE_LOCK",
    20011: "DRV_ERROR_PAGE_UNLOCK",
    20013: "DRV_ERROR_ACK",
    20024: "DRV_NO_NEW_DATA",
    20026: "DRV_SPOOL_ERROR",
    20034: "DRV_TEMP_OFF",
    20035: "DRV_TEMP_NOT_STABILIZED",
    20036: "DRV_TEMP_STABILIZED",
    20037: "DRV_TEMP_NOT_REACHED",
    20038: "DRV_TEMP_OUT_RANGE",
    20039: "DRV_TEMP_NOT_SUPPORTED",
    20040: "DRV_TEMP_DRIFT",
    20050: "DRV_COF_NOT_LOADED",
    20053: "DRV_FLEX_ERROR",
    20066: "DRV_P1INVALID",
    20067: "DRV_P2INVALID",
    20068: "DRV_P3INVALID",
    20069: "DRV_P4INVALID",
    20070: "DRV_INI_ERROR",
    20071: "DRV_CO_ERROR",
    20072: "DRV_ACQUIRING",
    20073: "DRV_IDLE",
    20074: "DRV_TEMP_CYCLE",
    20075: "DRV_NOT_INITIALIZED",
    20076: "DRV_P5INVALID",
    20077: "DRV_P6INVALID",
    20083: "P7_INVALID",
    20089: "DRV_USB_ERROR",
    20091: "DRV_NOT_SUPPORTED",
    20095: "DRV_INVALID_TRIGGER_MODE",
    20099: "DRV_BINNING_ERROR",
    20990: "DRV_NO_CAMERA",
    20991: "DRV_NOT_SUPPORTED",
    20992: "DRV_NOT_AVAILABLE"
}


class Main(Base, SpectroscopyCameraInterface):
    """ Hardware class for Andor CCD spectroscopy cameras

    Tested with :
     - Newton 940
    """
    _dll_location = ConfigOption('dll_location', missing='error')
    _close_shutter_on_deactivate = ConfigOption('close_shutter_on_deactivate', False)
    # todo: open shutter_on_activate ?

    _start_cooler_on_activate = ConfigOption('start_cooler_on_activate', True)
    _default_temperature = ConfigOption('default_temperature', 260)
    _default_trigger_mode = ConfigOption('default_trigger_mode', 'INTERNAL')
    _max_exposure_time = ConfigOption('max_exposure_time', 600)  # todo: does this come from the dll and why forbid it ?
    _shutter_TTL = ConfigOption('shutter_TTL', 1)  # todo: explain what this is for the user
    _shutter_switching_time = ConfigOption('shutter_switching_time', 100e-3)  # todo: explain what this is for the user

    _min_temperature = -85  # todo: why ? In this module internally, we can work with degree celsius, as andor users will be used to this. Still, this look rather arbitrary
    _max_temperature = -10  # todo: why ? same

    # Declarations of attributes to make Pycharm happy
    def __init__(self):
        self._constraints = None
        self._dll = None
        self._active_tracks = None
        self._image_advanced_parameters = None
        self._readout_speed = None
        self._read_mode = None
        self._trigger_mode = None
        self._shutter_status = None
        self._cooler_status = None
        self._temperature_setpoint = None

    ##############################################################################
    #                            Basic module activation/deactivation
    ##############################################################################
    def on_activate(self):
        """ Initialization performed during activation of the module. """
        try:
            self._dll = ct.cdll.LoadLibrary(self._dll_location)
        except OSError:
            self.log.error('Error during dll loading of the Andor camera, check the dll path.')
        # todo: camera selection by SN ?
        status_code = self._dll.Initialize()
        if status_code != OK_CODE:
            self.log.error('Problem during camera initialization')
            return

        self._constraints = self._build_constraints()

        if self._constraints.has_cooler and self._start_cooler_on_activate:
            self.set_cooler_on(True)

        self.set_read_mode(ReadMode.FVB)  # todo: what if not ?
        self.set_trigger_mode(self._default_trigger_mode)
        self.set_temperature_setpoint(self._default_temperature)

        self._set_acquisition_mode(AcquisitionMode.SINGLE_SCAN)
        self._active_tracks = []
        self._image_advanced_parameters = None

    def on_deactivate(self):
        """ De-initialisation performed during deactivation of the module. """
        if self.module_state() == 'locked':
            self.stop_acquisition()
        if self._close_shutter_on_deactivate:
            self.set_shutter_open_state(False)
        try:
            self._dll.ShutDown()
        except:
            self.log.warning('Error while shutting down Andor camera via dll.')

    ##############################################################################
    #                                     Error management
    ##############################################################################
    def _check(self, func_val):
        """ Check routine for the received error codes.

        @param (int) func_val: Status code returned by the DLL

        @return: The DLL function error code
        """
        if not func_val == OK_CODE:
            self.log.error('Error in Andor camera with error_code {}:{}'.format(func_val, ERROR_DICT[func_val]))
        return func_val

    ##############################################################################
    #                                     Constraints functions
    ##############################################################################
    def _build_constraints(self):
        """ Internal method that build the constraints once at initialisation

         This makes multiple call to the DLL, so it will be called only onced by on_activate
         """
        constraints = Constraints()
        constraints.name = self._get_name()
        constraints.width, constraints.width = self._get_image_size()
        constraints.pixel_size_width, constraints.pixel_size_width = self._get_pixel_size()
        constraints.internal_gains = [1, 2, 4]  # # todo : from hardware
        constraints.readout_speeds = [50000, 1000000, 3000000]  # todo : read from hardware
        constraints.has_cooler = True  # todo : from hardware ?
        constraints.trigger_modes = list(TriggerMode.__members__)  # todo : from hardware if only some are available ?
        constraints.has_shutter = True  # todo : from hardware ?
        constraints.read_modes = [ReadMode.FVB]
        if constraints.height > 1:
            constraints.read_modes.extend([ReadMode.MULTIPLE_TRACKS, ReadMode.IMAGE, ReadMode.IMAGE_ADVANCED])
        return constraints

    def get_constraints(self):
        """ Returns all the fixed parameters of the hardware which can be used by the logic.

        @return (Constraints): An object of class Constraints containing all fixed parameters of the hardware
        """
        return self._constraints

    ##############################################################################
    #                                     Basic functions
    ##############################################################################
    def start_acquisition(self):
        """ Starts the acquisition """
        self._check(self._dll.StartAcquisition())

    def _wait_for_acquisition(self):
        """ Internal function, can be used to wait till acquisition is finished """
        self._dll.WaitForAcquisition()

    def abort_acquisition(self):
        """ Aborts the acquisition """
        self._check(self._dll.AbortAcquisition())

    def get_ready_state(self):  # todo: check this function, i've guessed the dll behavior...
        """ Get the status of the camera, to know if the acquisition is finished or still ongoing.

        @return (bool): True if the camera is ready, False if an acquisition is ongoing

        As there is no synchronous acquisition in the interface, the logic needs a way to check the acquisition state.
        """
        code = ct.c_int()
        self._dll.GetStatus(ct.byref(code))
        if ERROR_DICT[code.value] == 'DRV_IDLE':
            return True
        elif ERROR_DICT[code.value] == 'DRV_ACQUIRING':
            return False
        else:
            self._check(code.value)

    def get_acquired_data(self):  # todo: test for every mode
        """ Return an array of last acquired data.

               @return: Data in the format depending on the read mode.

               Depending on the read mode, the format is :
               'FVB' : 1d array
               'MULTIPLE_TRACKS' : list of 1d arrays
               'IMAGE' 2d array of shape (width, height)
               'IMAGE_ADVANCED' 2d array of shape (width, height)

               Each value might be a float or an integer.
               """
        width = self.get_constraints().width
        if self.get_read_mode() == ReadMode.FVB:
            height = 1
        elif self.get_read_mode() == ReadMode.MULTIPLE_TRACKS:
            height = len(self.get_active_tracks())
        elif self.get_read_mode() == ReadMode.IMAGE:
            height = self.get_constraints().height
        elif self.get_read_mode() == ReadMode.IMAGE_ADVANCED:
            params = self.get_image_advanced_parameters()
            height = (params.vertical_end - params.vertical_start)/params.vertical_binning
            width = (params.horizontal_end - params.horizontal_start)/params.horizontal_binning

        dimension = int(width * height)
        c_image_array = ct.c_int * dimension
        c_image = c_image_array()
        status_code = self._dll.GetAcquiredData(ct.pointer(c_image), dimension)
        if status_code != OK_CODE:
            self.log.error('Could not retrieve data from camera. {0}'.format(ERROR_DICT[status_code]))

        if self.get_read_mode() == ReadMode.FVB:
            return np.array(c_image)
        else:
            return np.reshape(np.array(c_image), (width, height)).transpose()

    ##############################################################################
    #                           Read mode functions
    ##############################################################################
    def get_read_mode(self):
        """ Getter method returning the current read mode used by the camera.

        @return (ReadMode): Current read mode
        """
        return self._read_mode

    def set_read_mode(self, value):
        """ Setter method setting the read mode used by the camera.

         @param (ReadMode) value: read mode to set
         """

        if value not in self.get_constraints().read_modes:
            self.log.error('read_mode not supported')
            return

        conversion_dict = {ReadMode.FVB: ReadModeDLL.FVB,
                           ReadMode.MULTIPLE_TRACKS: ReadModeDLL.RANDOM_TRACK,
                           ReadMode.IMAGE: ReadModeDLL.IMAGE,
                           ReadMode.IMAGE_ADVANCED: ReadModeDLL.IMAGE}

        n_mode = conversion_dict[value].value
        status_code = self._check(self._dll.SetReadMode(n_mode))
        if status_code == OK_CODE:
            self._read_mode = value

        if value == ReadMode.IMAGE or value == ReadMode.IMAGE_ADVANCED:
            self._update_image()
        elif value == ReadMode.MULTIPLE_TRACKS:
            self._update_active_tracks()

    def get_readout_speed(self):
        """  Get the current readout speed (in Hz)

        @return (float): the readout_speed (Horizontal shift) in Hz
        """
        return self._readout_speed  # todo: not in dll ?

    def set_readout_speed(self, value):
        """ Set the readout speed (in Hz)

        @param (float) value: horizontal readout speed in Hz
        """
        if value in self.get_constraints().readout_speeds:
            readout_speed_index = self.get_constraints().readout_speeds.index(value)
            self._check(self._dll.SetHSSpeed(0, readout_speed_index))
            self._readout_speed = value
        else:
            self.log.error('Readout_speed value error, value {} is not in correct.'.format(value))

    def get_active_tracks(self):
        """ Getter method returning the read mode tracks parameters of the camera.

        @return (list):  active tracks positions [(start_1, end_1), (start_2, end_2), ... ]

        This getter is not available in the dll, so its state is handled by this module # todo: confirm ?
        """
        return self._active_tracks

    def set_active_tracks(self, value):
        """ Setter method for the active tracks of the camera.

        @param (list) value: active tracks positions  as [(start_1, end_1), (start_2, end_2), ... ]
        """
        if self.get_read_mode() != ReadMode.MULTIPLE_TRACKS:
            self.log.warning('Active tracks are defined outside of MULTIPLE_TRACKS mode.')

        self._active_tracks = value
        self._update_active_tracks()

    def _update_active_tracks(self):
        """ Internal function that send the current active tracks to the DLL """
        flatten_tracks = np.array(self._active_tracks).flatten()
        self._dll.SetRandomTracks.argtypes = [ct.c_int32, ct.c_void_p]
        status_code = self._check(self._dll.SetRandomTracks(len(self._active_tracks), flatten_tracks.ctypes.data))
        self._check(status_code)
        if status_code != OK_CODE:  # Clear tracks if an error has occurred
            self._active_tracks = []

    def get_image_advanced_parameters(self):
        """ Getter method returning the image parameters of the camera.

        @return (ImageAdvancedParameters): Current image advanced parameters

        Should only be used while in IMAGE_ADVANCED mode
        """
        return self._advanced_image_parameters

    def set_image_advanced_parameters(self, value):
        """ Setter method setting the read mode image parameters of the camera.

        @param (ImageAdvancedParameters) value: Parameters to set

        Should only be used while in IMAGE_ADVANCED mode
        """
        self._image_advanced_parameters = value
        self._update_image()

    def _update_image(self):
        """ Internal method that send the current appropriate image settings to the DLL"""

        if self.get_read_mode() == ReadMode.IMAGE:
            status_code = self._dll.SetImage(1, 1, 0, self.get_constraints().width, 0, self.get_constraints().height)
            self._check(status_code)

        elif self.get_read_mode() == ReadMode.IMAGE_ADVANCED:
            params = self._image_advanced_parameters
            status_code = self._dll.SetImage(int(params.horizontal_binning),  int(params.vertical_binning),
                                             int(params.horizontal_start), int(params.horizontal_end),
                                             int(params.vertical_start), int(params.vertical_end))
            self._check(status_code)

    ##############################################################################
    #                           Acquisition mode functions
    ##############################################################################
    def _get_acquisition_mode(self):
        """ Getter method returning the current acquisition mode used by the camera.

        @return (str): acquisition mode
        """
        return self._acquisition_mode

    def _set_acquisition_mode(self, value):
        """ Setter method setting the acquisition mode used by the camera.

        @param (str|AcquisitionMode): Acquisition mode as a string or an object

        This method is not part of the interface, so we might need to use it from a script directly. Hence, here
        it is worth it to accept a string.
        """
        if isinstance(value, str) and value in AcquisitionMode.__members__:
            value = AcquisitionMode[value]
        if not isinstance(value, AcquisitionMode):
            self.log.error('{} acquisition mode is not supported'.format(value))
            return
        n_mode = ct.c_int(value.value)
        self._check(self._dll.SetAcquisitionMode(n_mode))

    def get_exposure_time(self):
        """ Get the exposure time in seconds

        @return (float) : exposure time in s
        """
        return self._get_acquisition_timings()['exposure']

    def _get_acquisition_timings(self):
        """ Get the acquisitions timings from the dll

        @return (dict): dict containing keys 'exposure', 'accumulate', 'kinetic' and their values in seconds """
        exposure, accumulate, kinetic = ct.c_float(), ct.c_float(), ct.c_float()
        self._check(self._dll.GetAcquisitionTimings(ct.byref(exposure), ct.byref(accumulate), ct.byref(kinetic)))
        return {'exposure': exposure.value, 'accumulate': accumulate.value, 'kinetic': kinetic.value}

    def set_exposure_time(self, value):
        """ Set the exposure time in seconds

        @param (float) value: desired new exposure time
        """
        if value < 0:
            self.log.error('Exposure_time ({} s) can not be negative.'.format(value))
            return
        if value > self._max_exposure_time:
            self.log.error('Exposure time ({} s) is above the high limit ({} s)'.format(value, self._max_exposure_time))
            return
        self._check(self._dll.SetExposureTime(ct.c_float(value)))

    def get_gain(self):
        """ Get the gain

        @return (float): exposure gain
        """
        return self._preamp_gain  # todo: read from hardware ?

    def set_gain(self, value):
        """ Set the gain

        @param (float) value: New gain, value should be one in the constraints internal_gains list.
        """
        if value not in self.get_constraints().internal_gains:
            self.log.error('gain value {} is not available.'.format(value))
            return
        gain_index = self.get_constraints().internal_gains.index(value)
        self._check(self._dll.SetPreAmpGain(gain_index))

    ##############################################################################
    #                           Trigger mode functions
    ##############################################################################
    def get_trigger_mode(self):
        """ Getter method returning the current trigger mode used by the camera.

        @return (str): current trigger mode
        """
        return self._trigger_mode  # todo: read from hardware ?

    def set_trigger_mode(self, value):
        """ Setter method for the trigger mode used by the camera.

        @param (str) value: trigger mode (must be compared to a dict)
        """
        if value not in self.get_constraints().trigger_modes:
            self.log.error('Trigger mode {} is not declared by hardware.'.format(value))
            return
        n_mode = TriggerMode[value].value
        status_code = self._check(self._dll.SetTriggerMode(n_mode))
        if status_code == OK_CODE:
            self._trigger_mode = value

    ##############################################################################
    #                           Shutter mode functions
    ##############################################################################
    def get_shutter_open_state(self):
        """ Getter method returning the shutter mode.

        @return (bool): True if the shutter is open, False of closed
        """
        if not self.get_constraints().has_shutter:
            self.log.error('Can not get state of the shutter, camera does not have a shutter')
        return self._shutter_status  # todo from hardware

    def set_shutter_open_state(self, value):
        """ Setter method setting the shutter mode.

        @param (bool) value: True to open, False tp close
        """
        if not self.get_constraints().has_shutter:
            self.log.error('Can not set state of the shutter, camera does not have a shutter')
        mode = ShutterMode.OPEN if value else ShutterMode.CLOSE
        mode = ct.c_int(mode.value)  # todo: needed for interger ?
        shutter_TTL = int(self._shutter_TTL)
        shutter_time = int(round(self._shutter_switching_time*1e3))  # DLL use ms
        status_code = self._check(self._dll.SetShutter(shutter_TTL, mode, shutter_time, shutter_time))
        if status_code == OK_CODE:
            self._shutter_status = value

    ##############################################################################
    #                           Temperature functions
    ##############################################################################
    def get_cooler_on(self):
        """ Getter method returning the cooler status

        @return (bool): True if the cooler is on
        """
        return self._cooler_status  # todo: from harware

    def set_cooler_on(self, value):
        """ Setter method for the the cooler status

        @param (bool) value: True to turn it on, False to turn it off
        """
        if value:
            status_code = self._dll.CoolerON()
        else:
            status_code = self._dll.CoolerOFF()
        self._check(status_code)
        if status_code == OK_CODE:
            self._cooler_status = value  # todo: no need if handled by hardware

    def get_temperature(self):
        """ Getter method returning the temperature of the camera.

        @return (float): temperature (in Kelvin)

        The dll uses integers in celsius, so the result will always end with .15, too bad.
        """
        temp = ct.c_int32()
        self._dll.GetTemperature(ct.byref(temp))
        return temp.value + 273.15

    def get_temperature_setpoint(self):
        """ Getter method for the temperature setpoint of the camera.

        @return (float): Current setpoint in Kelvin
        """
        return self._temperature_setpoint  #todo: not in dll ?

    def set_temperature_setpoint(self, value):
        """ Setter method for the the temperature setpoint of the camera.

        @param (float) value: New setpoint in Kelvin
        """
        temperature = int(round(value + 273.15))
        if not(self._min_temperature < temperature < self._max_temperature):
            self.log.error('Temperature {}°C is not in the validity range.')
            return
        status_code = self._check(self._dll.SetTemperature(temperature))
        if status_code == OK_CODE:
            self._temperature_setpoint = temperature

    ##############################################################################
    #               Internal functions, for constraints preparation
    ##############################################################################
    def _get_serial_number(self):
        """ Get the serial number of the camera as a string

        @return (str): serial number of the camera
        """
        serial = ct.c_int()
        self._check(self._dll.GetCameraSerialNumber(ct.byref(serial)))
        return serial.value

    def _get_name(self):
        """ Get a name for the camera

        @return (str): local camera name with serial number
        """
        return "Camera SN: {}".format(self._get_serial_number())

    def _get_image_size(self):
        """ Returns the sensor size in pixels (width, height)

        @return tuple(int, int): number of pixel in width and height
        """
        nx_px = ct.c_int()
        ny_px = ct.c_int()
        self._check(self._dll.GetDetector(ct.byref(nx_px), ct.byref(ny_px)))
        return nx_px.value, ny_px.value

    def _get_pixel_size(self):
        """ Get the physical pixel size (width, height) in meter

        @return tuple(float, float): physical pixel size in meter
        """
        x_px = ct.c_float()
        y_px = ct.c_float()
        self._check(self._dll.GetPixelSize(ct.byref(x_px), ct.byref(y_px)))
        return y_px.value * 1e-6, x_px.value * 1e-6

    def _get_current_config(self):
        """ Internal helper method to get the camera parameters in a printable dict.

        @return (dict): dictionary with camera current configuration.
        """
        config = {  #todo use getters for most of them
            'camera ID..................................': self._get_name(),
            'sensor size (pixels).......................': self._get_image_size(),
            'pixel size (m)............................': self._get_pixel_size(),
            'acquisition mode...........................': self._acquisition_mode,
            'read mode..................................': self._read_mode,
            'readout speed (Hz).........................': self._readout_speed,
            'gain (x)...................................': self._preamp_gain,
            'trigger_mode...............................': self._trigger_mode,
            'exposure_time..............................': self._exposure,
            'ROI geometry (readmode = IMAGE)............': self._ROI,
            'ROI binning (readmode = IMAGE).............': self._binning,
            'tracks definition (readmode = RANDOM TRACK)': self._active_tracks,
            'temperature (K)............................': self._temperature,
            'shutter_status.............................': self._shutter_status,
        }
        return config