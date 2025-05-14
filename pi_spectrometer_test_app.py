'''
Created on May 14, 2025

@author: Edward Barnard, Benedikt Ursprung
'''

from ScopeFoundry.base_app import BaseMicroscopeApp


class TestApp(BaseMicroscopeApp):

    name = "pi_spectrometer_test_app"

    def setup(self):
        
        from ScopeFoundryHW.princeton_instruments_spectrometers import PISpectrometerHW
        self.add_hardware(PISpectrometerHW(self))



if __name__ == '__main__':
    import sys
    app = TestApp(sys.argv)
    sys.exit(app.exec_())
