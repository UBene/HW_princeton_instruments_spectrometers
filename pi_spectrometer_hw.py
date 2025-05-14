"""
Created on May 28, 2014

@author: Edward Barnard, Benedikt Ursprung

updated 2017-12-06
updated 2023-02-26 Benedikt added calib_params from_dev option
"""

import numpy as np

from ScopeFoundry import HardwareComponent

CALIB_PARAM_DESCRIPTION = """use <i>from_grating_calibrations</i> 
if calibrations was done manually and loaded to <b>grating_calibrations</b> via a settings file.
Use <i>from_dev</i> if calibrations was done in e.g. Lightfield and params stored to device"""


class PISpectrometerHW(HardwareComponent):

    name = "pi_spectrometer"

    def __init__(
        self,
        app,
        debug=False,
        name=None,
        front_exit_name="Front (CCD)",
        side_exit_name="Side (APD)",
    ):
        self.exit_mirror_choices = [
            (front_exit_name, "FRONT"),
            (side_exit_name, "SIDE"),
        ]
        super().__init__(app, debug, name)

    def setup(self):

        # Create logged quantities
        self.settings.New("port", dtype=str, initial="COM3")
        # if serial port echo is enabled, USB echo should be disabled
        self.settings.New("echo", dtype=bool, initial=True)

        self.settings.New(
            name="center_wl",
            dtype=float,
            fmt="%1.3f",
            ro=False,
            unit="nm",
            si=False,
            vmin=-100,
            vmax=2000,
            spinbox_decimals=3,
            reread_from_hardware_after_write=True,
        )

        self.settings.New(
            "grating_id", dtype=int, initial=1, choices=(1, 2, 3, 4, 5, 6)
        )
        self.settings.New("grating_name", dtype=str, ro=True)

        self.settings.New("exit_mirror", str, choices=self.exit_mirror_choices)
        self.settings.New(
            "entrance_slit", dtype=int, unit="um", reread_from_hardware_after_write=True
        )
        self.settings.New(
            "exit_slit", dtype=int, unit="um", reread_from_hardware_after_write=True
        )

        self.settings.New(
            "calib_param",
            str,
            choices=("from_grating_calibrations", "from_dev"),
            description=CALIB_PARAM_DESCRIPTION,
        )

        # f (nm), delta (angle), gamma(angle), n0, d_grating(nm), x_pixel(nm),
        # distances stored in nm
        self.settings.New(
            "grating_calibrations",
            dtype=float,
            array=True,
            initial=[[300e6, 0, 0, 256, 0, (1 / 150.0) * 1e6, 16e3, 0]] * 3,
        )

        # self.settings.New('model', str, ro=True)
        # self.settings.New('serial', str, ro=True)

        self.add_operation("test_wl_calibration", self.test_wl_calibration)

    def New_quick_UI(
        self,
        include=("connected", "center_wl", "grating_id", "exit_mirror"),
        operations=[],
    ):
        from qtpy import QtWidgets

        widget = QtWidgets.QGroupBox(title=self.name)
        layout = QtWidgets.QVBoxLayout(widget)
        layout.addWidget(self.settings.New_UI(include))
        widget.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Maximum
        )
        for op in operations:
            layout.addWidget(self.new_operation_push_buttons(op))
        return widget

    def connect(self):

        s = self.settings
        if s["debug_mode"]:
            self.log.info("connecting to dev")

        from .pi_spectrometer_dev import PISpectrometerDev

        self.dev = PISpectrometerDev(
            port=s["port"], echo=s["echo"], debug=s["debug_mode"], dummy=False
        )

        s.grating_id.change_choice_list(
            tuple(
                [("{}: {}".format(num, name), num) for num, name in self.dev.gratings]
            )
        )

        s.get_lq("center_wl").connect_to_hardware(
            read_func=self.dev.read_wl, write_func=self.dev.write_wl_fast
        )

        s.get_lq("exit_mirror").connect_to_hardware(
            read_func=self.dev.read_exit_mirror, write_func=self.dev.write_exit_mirror
        )

        s.get_lq("grating_name").connect_to_hardware(
            read_func=self.dev.read_grating_name
        )

        s.get_lq("grating_id").connect_to_hardware(
            read_func=self.dev.read_grating, write_func=self.dev.write_grating
        )

        s.get_lq("entrance_slit").connect_to_hardware(
            read_func=self.dev.read_entrance_slit,
            write_func=self.dev.write_entrance_slit,
        )

        s.get_lq("exit_slit").connect_to_hardware(
            read_func=self.dev.read_exit_slit,
            write_func=self.dev.write_exit_slit,
        )

        # S['serial'] = self.dev.read_serial()
        # S['model'] = self.dev.read_model()

        print(
            "connecting to",
            self.dev.read_model(),
            "serial number",
            self.dev.read_serial(),
        )

        self.read_from_hardware()
        self.dev_calib_params = self.dev.read_calibration_params()
        self.gratings = self.dev.gratings_dict

    def disconnect(self):
        self.log.info("disconnect " + self.name)
        self.settings.disconnect_all_from_hardware()

        if hasattr(self, "dev"):
            self.dev.close()
            del self.dev

    def get_wl_calibration(self, px_index, binning=1, m_order=1, pixel_width=16):
        s = self.settings

        if s["calib_param"] == "from_grating_calibrations":
            grating_id = s["grating_id"] - 1
            grating_calib_array = s["grating_calibrations"][grating_id]
            f, delta, gamma, n0, offset_adjust, d_grating, x_pixel = (
                grating_calib_array[0:7]
            )
            curvature = 0
            if len(grating_calib_array) > 7:
                curvature = grating_calib_array[7]
            binned_px = binning * px_index + 0.5 * (binning - 1)
            return wl_p_calib(
                binned_px,
                n0,
                offset_adjust,
                s["center_wl"],
                m_order,
                d_grating,
                x_pixel,
                f,
                delta,
                gamma,
                curvature,
            )
        else:
            grooves = self.gratings[s["grating_id"]]["grooves"]
            if grooves == 0:  # is probably a mirror
                return px_index
            cols = len(px_index)
            return calc_disp(
                self.dev_calib_params,
                m_order,
                s["center_wl"],
                grooves,
                cols,
                pixel_width,
            )

    def test_wl_calibration(self):
        px_index = np.arange(1600)
        print(self.get_wl_calibration(px_index, 1, 1, 16))


def wl_p_calib(
    px,
    n0,
    offset_adjust,
    wl_center,
    m_order,
    d_grating,
    x_pixel,
    f,
    delta,
    gamma,
    curvature=0,
):
    # print('wl_p_calib:', px, n0, offset_adjust, wl_center, m_order, d_grating, x_pixel, f, delta, gamma, curvature)
    # consts
    # d_grating = 1./150. #mm
    # x_pixel   = 16e-3 # mm
    # m_order   = 1 # diffraction order, unitless
    n = px - (n0 + offset_adjust * wl_center)

    # print('psi top', m_order* wl_center)
    # print('psi bottom', (2*d_grating*np.cos(gamma/2)) )

    psi = np.arcsin(m_order * wl_center / (2 * d_grating * np.cos(gamma / 2)))
    eta = np.arctan(n * x_pixel * np.cos(delta) / (f + n * x_pixel * np.sin(delta)))

    return (
        (d_grating / m_order)
        * (np.sin(psi - 0.5 * gamma) + np.sin(psi + 0.5 * gamma + eta))
    ) + curvature * n**2


def calc_disp(dev_calib_params, m_order, center_wl, grooves, cols, pixel_width):
    # convert dimensions to meter and radians
    d = (1 / grooves) * 1e-3
    f = dev_calib_params["focal length"] * 1e-3
    w = pixel_width * 1e-6
    cwl = center_wl * 1e-9
    da = np.radians(dev_calib_params["detector angle"])
    ha = np.radians(dev_calib_params["half angle"])

    n = np.linspace(-(cols // 2), (cols // 2) - int(cols % 2 == 0), cols)
    offset_angle = np.arctan((n * w * np.cos(da)) / (f + n * w * np.sin(da)))
    grat_angle = np.arcsin(m_order * cwl / (2 * d * np.cos(ha)))
    # convert to nm
    return (
        (d / m_order)
        * (np.sin(grat_angle - ha) + np.sin(grat_angle + ha + offset_angle))
        * 1e9
    )
