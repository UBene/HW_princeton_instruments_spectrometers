import logging
import re
import time

import serial

logger = logging.getLogger(__name__)


class PISpectrometerDev:

    def __init__(self, port, debug=False, echo=True, dummy=False):

        self.debug = debug
        self.dummy = dummy
        self.echo = echo  # unused! ToDo add it.

        if not self.dummy:
            self.ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=8,
                parity="N",
                stopbits=1,
                xonxoff=0,
                rtscts=0,
                timeout=5.0,
            )

            self.ser.flushInput()
            self.ser.flushOutput()
        # self.write_command("MONO-RESET")
        # self.read_serial()
        # self.read_model()
        self.read_grating_info()

    def read_done_status(self):
        # returns either 1 or 0 for done or not done
        resp = self.write_command("MONO-?DONE")
        return bool(int(resp))

    def read_wl(self):
        resp = self.write_command("?NM")
        self.wl = float(resp.split()[0])
        return self.wl

    def write_wl(self, wl, waittime=1.0):
        wl = float(wl)
        resp = self.write_command("%0.3f NM" % wl, waittime=waittime)
        if self.debug:
            logger.debug("write_wl wl:{} resp:{}".format(wl, resp))

    def write_wl_fast(self, wl, waittime=1.0):
        wl = float(wl)
        resp = self.write_command("%0.3f GOTO" % wl, waittime=waittime)
        if self.debug:
            logger.debug("write_wl_fast wl:{} resp:{}".format(wl, resp))

    def write_wl_nonblock(self, wl):
        wl = float(wl)
        resp = self.write_command("%0.3f >NM" % wl)
        if self.debug:
            logger.debug("write_wl_nonblock wl:{} resp:{}".format(wl, resp))

    def read_grating_info(self):
        grating_string = self.write_command("?GRATINGS", waittime=1.0)
        """
            \x1a1  300 g/mm BLZ=  500NM 
            2  300 g/mm BLZ=  1.0UM 
            3  150 g/mm BLZ=  500NM 
            4  Not Installed     
            5  Not Installed     
            6  Not Installed     
            7  Not Installed     
            8  Not Installed     
            9  Not Installed     
            ok
        """
        # 0x1A is the arrow char, indicates selected grating

        self.gratings = []
        self.gratings_dict = {}
        for line in grating_string.splitlines():
            l = (re.sub(" {2,}", " ", line).rstrip().lstrip()).strip("\x1a").split(" ")
            if len(l) == 5:
                self.gratings.append((l[0], " ".join(l[1:])))
                self.gratings_dict[int(l[0])] = {
                    "id": int(l[0]),
                    "grooves": int(l[1]),
                    "blaze": l[4],
                }

            if len(l) == 2 and l[1] == "Mirror":
                self.gratings.append((l[0], "Mirror"))
                self.gratings_dict[int(l[0])] = {
                    "id": int(l[0]),
                    "grooves": 0,
                    "blaze": 0,
                }

        return self.gratings

    def read_turret(self):
        resp = self.write_command("?TURRET")
        self.turret = int(resp)
        return self.turret

    def write_turret(self, turret):
        assert turret in [1, 2, 3]
        self.write_command("%i TURRET" % turret)

    def read_grating(self):
        resp = self.write_command("?GRATING")
        self.grating = int(resp)
        return self.grating

    def read_grating_name(self):
        self.read_grating()
        return self.gratings[self.grating - 1]

    def write_grating(self, grating):
        assert 0 < grating < 10
        self.write_command("%i GRATING" % grating)

    def read_exit_mirror(self):
        resp = self.write_command("EXIT-MIRROR ?MIRROR")
        self.exit_mirror = resp.upper()
        return self.exit_mirror

    def write_exit_mirror(self, pos):
        pos = pos.upper()
        assert pos in ["FRONT", "SIDE"]
        self.write_command("EXIT-MIRROR %s" % pos)

    def read_entrance_slit(self):
        resp = self.write_command("SIDE-ENT-SLIT ?MICRONS")
        resp = resp.strip()
        if self.debug:
            print(resp)
        # "480 um" or "no motor"
        if resp in ["no motor", "no slit"]:
            self.entrance_slit = -1
        else:
            self.entrance_slit = int(resp.split()[0])
        return self.entrance_slit

    def write_entrance_slit(self, pos):
        assert 5 <= pos <= 3000
        self.write_command("SIDE-ENT-SLIT %i MICRONS" % pos)
        # should return new pos

    def home_entrance_slit(self):
        # TODO
        "SIDE-ENT-SLIT SHOME"

    def read_exit_slit(self):
        resp = self.write_command("SIDE-EXIT-SLIT ?MICRONS")
        resp = resp.strip()
        # "960 um" or "no motor"
        if resp in ["no motor", "no slit"]:
            self.exit_slit = -1
        else:
            self.exit_slit = int(resp.split()[0])
        return self.exit_slit

    def write_exit_slit(self, pos):
        assert 5 <= pos <= 3000
        self.write_command("SIDE-EXIT-SLIT %i MICRONS" % pos)

    #    def write_command(self, cmd):
    #        if self.debug: print "write_command:", cmd
    #        self.ser.write(cmd + "\r\n")
    #        response = self.ser.readline()
    #        if self.debug: print "\tresponse:", repr(response)
    #        assert response[-4:] == "ok\r\n"
    #        return response[:-4].strip()

    def write_command(self, cmd, waittime=0.01):
        if self.debug:
            logger.debug("write_command cmd: {}".format(cmd))
            print("write_command cmd: {}".format(cmd))

        if self.dummy:
            return "0"
        cmd_bytes = cmd.encode("latin-1")
        self.ser.write(cmd_bytes + b"\r")
        time.sleep(waittime)
        return self.read_buffer()

    def read_buffer(self):
        SENTINEL = b" ok\r\n"
        out = bytearray("12345", "latin-1")
        missed_char_count = 0

        while out[-5:] != SENTINEL:
            char = self.ser.read()
            # if self.debug: print("readbyte", repr(char))
            if char == b"":  # handles a timeout here
                missed_char_count += 1
                if self.debug:
                    logger.debug(
                        "no character returned, missed %i so far" % missed_char_count
                    )
                if missed_char_count > 3:
                    return 0
                continue
            out += char

        if self.debug:
            logger.debug(f"response {repr(out[5:])}")
            print(f"response {repr(out[5:])}")

        assert out[-5:] == SENTINEL
        return out[5:-5].decode("latin-1").strip()

    def read_calibration_params(self):
        resp = self.write_command("MONO-EESTATUS")

        if self.debug:
            for line in resp.split("\r\n"):
                print(line)

        lines = [
            str.rstrip(re.sub(" {2,}", " ", r)) for r in resp.split("\r\n") if r != ""
        ]

        params = {}
        # parse scalars
        for key in ("grating", "focal length", "half angle", "detector angle"):
            params[key] = parse_scalar(key, lines)
        # parse 1D arrays
        for key in ("offset", "adjust"):
            params[key] = parse_array(key, lines)

        if self.debug:
            logger.debug("calibration params", params)

            print("calibration params:")
            for k, v in params.items():
                print(k, v)

        return params

    def read_model(self):
        return self.write_command("MODEL")

    def read_serial(self):
        return self.write_command("SERIAL")

    def close(self):
        self.ser.close()


def parse_scalar(key, lines):
    for line in lines:
        if line.startswith(key):
            return float(line.split(" ")[-1])


def parse_array(key, lines):
    for line in lines:
        if line.startswith(key):
            return [int(v) for v in re.sub(" {2,}", " ", line).split(" ")[1:]]
