# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.printer import PrinterInterface
from octoprint.events import Events
from octoprint.util import RepeatedTimer, ResettableTimer, get_formatted_datetime, get_formatted_timedelta

from octoprint_lcdproc.lcdproc.server import Server

from pprint import pprint
from datetime import datetime, timedelta

ETA_FORMAT="%H:%M:%S"
FIN_FORMAT="%0%H:%M"

class LcdprocPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.ProgressPlugin
):

    lcd = None
    timer_screen = None
    timer_seconds = None
    start_timestamp = None

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            # put your plugin's default settings here
        }

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/lcdproc.js"],
            "css": ["css/lcdproc.css"],
            "less": ["less/lcdproc.less"]
        }

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "lcdproc": {
                "displayName": self._plugin_name,
                "displayVersion": self._plugin_name,

                # version check: github repository
                "type": "jsondata",
                "jsondata": "https://git.czo.hu/czo/octoprint-lcdproc/-/raw/main/softwareupdate.json?inline=false",

                # update method: pip
                "pip": "https://git.czo.hu/czo/octoprintlcdproc/-/archive/{target}/octoprint-lcdproc-{target}.zip",
                "release_notes": "https://git.czo.hu/czo/octoprintlcdproc/-/tree/{target_version}",
            }
        }

    def on_startup(self, host, port):
        self.initialize_lcd()

    def on_shutdown(self):
        print("!CZO! -- !!!!! - on_shutdown")

    def on_event(self, event, payload):
        if event in [ Events.PRINT_STARTED, Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_FAILED, ]:
            if self.timer_screen:
                self.timer_screen.cancel()
                self.timer_screen = None

            if not self.timer_seconds:
                self.timer_seconds = RepeatedTimer( 1.0, self.on_timer_seconds )

            if event in [ Events.PRINT_STARTED, ]:
                self.lcd.screens['OctPriSCR1'].set_priority("foreground")
                self.lcd.screens['OctPriSCR1'].widgets['TextFileName'].set_text( payload['name'] )
                self.lcd.screens['OctPriSCR1'].widgets['TextFileName'].update()
                self.start_timestamp = datetime.now()
                if not self.timer_seconds.is_alive():
                    self.timer_seconds.start()
                if not self.timer_seconds.is_alive():
                    self.timer_seconds.start()

            if event in [ Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_FAILED, ]:
                self.lcd.screens['OctPriSCR1'].set_priority("info")
                self.start_timestamp = None
                self.timer_screen = ResettableTimer( 3600, self.on_timer_screen )
                self.timer_screen.start()
                self.timer_seconds.cancel()

    def on_print_progress(self, storage, path, progress ):
        PERCENT_STR = "%d%%" % ( progress )
        self.lcd.screens['OctPriSCR1'].widgets['TextPercent'].set_text( PERCENT_STR )
        self.lcd.screens['OctPriSCR1'].widgets['TextPercent'].set_x( self.lcd.server_info['screen_width'] - ( len( PERCENT_STR ) - 1 ) )
        self.lcd.screens['OctPriSCR1'].widgets['TextPercent'].update()

    def on_timer_seconds(self):
        try:
            ETA_SECONDS = self._printer.get_current_data()['progress']['printTimeLeft']
        except:
            ETA_SECONDS = None

        if ETA_SECONDS is not None and self.start_timestamp:
            # ETA
            CURRENT_ETA_FORMAT = ETA_FORMAT
            FINISH_DATETIME_CUT = datetime(1,1,1,0,0,0,0) + timedelta( seconds = ETA_SECONDS if ETA_SECONDS < 360000 else 360000 )
            self.lcd.screens['OctPriSCR1'].widgets['TextETA'].set_text( FINISH_DATETIME_CUT.strftime(CURRENT_ETA_FORMAT) )
            self.lcd.screens['OctPriSCR1'].widgets['TextETA'].update()

            # FIN
            CURRENT_FIN_FORMAT = FIN_FORMAT
            FINISH_DATETIME = datetime.now() + timedelta( seconds = ETA_SECONDS )

            START_DATE = self.start_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            FIN_DATE = FINISH_DATETIME.replace(hour=0, minute=0, second=0, microsecond=0)

            if "%0" in CURRENT_FIN_FORMAT:
                if ( (FIN_DATE-START_DATE).days == 0 ):
                    CURRENT_FIN_FORMAT = CURRENT_FIN_FORMAT.replace("%0", "" )
                else:
                    EXTRA_DAYS = "+%d " % ( (FIN_DATE-START_DATE).days )
                    CURRENT_FIN_FORMAT = CURRENT_FIN_FORMAT.replace("%0", EXTRA_DAYS )

            CURRENT_FIN_TEXT = FINISH_DATETIME.strftime(CURRENT_FIN_FORMAT)
            self.lcd.screens['OctPriSCR1'].widgets['TextFIN'].set_text( CURRENT_FIN_TEXT )
            self.lcd.screens['OctPriSCR1'].widgets['TextFIN'].set_x( self.lcd.server_info['screen_width'] - len( CURRENT_FIN_TEXT ) )
            self.lcd.screens['OctPriSCR1'].widgets['TextFIN'].update()

    def on_timer_screen(self):
        self.timer_screen = None
        self.lcd.screens['OctPriSCR1'].set_priority("hidden")
        print("!CZO! -- !!!!! - on_timer_screen" )

    def initialize_lcd(self):
        self.lcd = Server(hostname="127.0.0.1", port=13666, debug=False)
        self.lcd.start_session()

        self.lcd.add_screen("OctPriSCR1")
        self.lcd.screens['OctPriSCR1'].set_heartbeat("off")
        self.lcd.screens['OctPriSCR1'].set_priority("hidden")
        self.lcd.screens['OctPriSCR1'].add_string_widget("TextPercent", text="", y=1, x=self.lcd.server_info['screen_width']-3 )
        self.lcd.screens['OctPriSCR1'].add_scroller_widget("TextFileName", text="", speed=5, left=1, top=1, right=self.lcd.server_info['screen_width']-5, bottom=1 )
        self.lcd.screens['OctPriSCR1'].add_icon_widget("IconETA", x=1, y=2, name="SELECTOR_AT_RIGHT" )
        self.lcd.screens['OctPriSCR1'].add_icon_widget("IconFIN", x=self.lcd.server_info['screen_width'], y=2, name="SELECTOR_AT_LEFT" )
        self.lcd.screens['OctPriSCR1'].add_string_widget("TextETA", text="", y=2,x=2,)
        self.lcd.screens['OctPriSCR1'].add_string_widget("TextFIN", text="", y=2,x=self.lcd.server_info['screen_width']-2)

__plugin_name__ = "LCDproc"
__plugin_version__ = "0.0.9"
__plugin_description__ = """LCDd/LCDproc support for status/progress reporting"""
__plugin_author__ = "Jozsef CZOMPO"
__plugin_author_email__ = "czo@czo.hu"
__plugin_url__ = "https://git.czo.hu/czo/octoprint-lcdproc"
__plugin_license__ = "GPLv3"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
__plugin_pythoncompat__ = ">=3.4,<4"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = LcdprocPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
