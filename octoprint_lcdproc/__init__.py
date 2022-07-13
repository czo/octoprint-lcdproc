# coding=utf-8
from __future__ import absolute_import
from datetime import datetime, timedelta

import octoprint.plugin
from octoprint.printer import PrinterInterface
from octoprint.events import Events
from octoprint.util import RepeatedTimer, ResettableTimer, get_formatted_datetime, get_formatted_timedelta

from octoprint_lcdproc.lcdproc.server import Server

STATE_NON_PRINTING = "non_printing"
STATE_PRINTING = "printing"
STATE_IDLE = "idle"

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
    screen_priority_state = STATE_IDLE
    start_timestamp = None
    printing_filename = None
    printing_percent = None
    printing_eta = None

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
                "displayVersion": self._plugin_version,
                "current": self._plugin_version,

                "type": "jsondata",
                "jsondata": "https://raw.githubusercontent.com/czo/octoprint-lcdproc/main/softwareupdate.json",

                "method": "pip",
                "pip": "https://github.com/czo/octoprint-lcdproc/archive/refs/tags/{target}.zip",
                "release_notes": "https://github.com/czo/octoprint-lcdproc/blob/main/CHANGELOG.md",
            }
        }

    def get_settings_defaults(self):
        return {
            "enabled": True,
            "host": "localhost",
            "port": 13666,
            "hide_page_when_idle": True,
            "priority_printing": "foreground",
            "priority_non_printing": "info",
            "idle_time_minutes": 60,
            "title_show": False,
            "title_text": "OctoPrint",
        }

    def get_template_configs(self):
        return [
            {
                "type": "settings",
                "custom_bindings": False,
            }
        ]

    def on_settings_save(self, data):
        anything_changed = False
        current_values = self.get_settings_defaults()
        for key in self.get_settings_defaults().keys():
            current_values[key] = self._settings.get([key])
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        for key in self.get_settings_defaults().keys():
            if not current_values[key] == self._settings.get([key]):
                anything_changed = True
                break

        if anything_changed:
            self._logger.info("Configuration changed, destroying connection")
            if self.lcd:
                self.lcd.close_session()
                self.lcd = None

    def on_startup(self, host, port):
        self.initialize_lcd()

    def on_event(self, event, payload):
        if event in [ Events.PRINT_STARTED, Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_FAILED, ]:
            if self.timer_screen:
                self.timer_screen.cancel()
                self.timer_screen = None

            if not self.timer_seconds:
                self.timer_seconds = RepeatedTimer( 15.0, self.on_timer_seconds )

            if event in [ Events.PRINT_STARTED, ]:
                self.screen_priority_state = STATE_PRINTING
                self.printing_filename = payload['name']
                self.start_timestamp = datetime.now()
                self.update_screen_TextFileName()
                self.update_screen_TextETA()
                self.update_screen_TextPercent()
                self.update_screen_TextFIN()

                if not self.timer_seconds.is_alive():
                    self.timer_seconds.start()

                self.update_screen_priority()

            if event in [ Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_FAILED, ]:
                self.screen_priority_state = STATE_NON_PRINTING
                self.start_timestamp = None
                self.printing_eta = None
                self.printing_percent = None

                self.timer_seconds.cancel()
                self.timer_seconds = None

                if self._settings.get_boolean(["hide_page_when_idle"]):
                    self.timer_screen = ResettableTimer( 60 * self._settings.get_int(["idle_time_minutes"]), self.on_timer_screen )
                    self.timer_screen.start()

                self.update_screen_priority()

    def update_screen_TextFileName(self):
        if self.printing_filename is None:
            visible_filename = " - "
        else:
            visible_filename = self.printing_filename

        screen, screen_width, screen_height = self.ensure_screen('OctPriSCR1')
        if screen and 'TextFileName' in screen.widgets:
            self._logger.info("LCDd 'TextFileName' == '%s'" % visible_filename )
            screen.widgets['TextFileName'].set_text( visible_filename )
            screen.widgets['TextFileName'].update()

    def update_screen_priority(self):
        screen, screen_width, screen_height = self.ensure_screen('OctPriSCR1')
        if screen:
            if self.screen_priority_state == STATE_IDLE:
                if self._settings.get_boolean(["hide_page_when_idle"]):
                    self._logger.info("Switching screen priority: hidden")
                    self.lcd.screens['OctPriSCR1'].set_priority("hidden")
                else:
                    self.screen_priority_state = STATE_NON_PRINTING

            if self.screen_priority_state == STATE_NON_PRINTING:
                new_priority = self._settings.get(["priority_non_printing"])
                self._logger.info("Switching screen priority: %s" % new_priority )
                self.lcd.screens['OctPriSCR1'].set_priority( new_priority )

            if self.screen_priority_state == STATE_PRINTING:
                new_priority = self._settings.get(["priority_printing"])
                self._logger.info("Switching screen priority: %s" % new_priority )
                self.lcd.screens['OctPriSCR1'].set_priority( new_priority )

    def update_screen_TextPercent(self):
        if self.printing_percent is None:
            visible_percent = " - "
        else:
            visible_percent = "%d%%" % ( self.printing_percent )

        screen, screen_width, screen_height = self.ensure_screen('OctPriSCR1')
        if screen and 'TextPercent' in screen.widgets:
            self._logger.info("LCDd 'TextPercent' == '%s'" % visible_percent )
            screen.widgets['TextPercent'].set_text( visible_percent )
            screen.widgets['TextPercent'].set_x( screen_width - ( len( visible_percent ) - 1 ) )
            screen.widgets['TextPercent'].update()

    def update_screen_TextETA( self ):
        if self.printing_eta is None:
            visible_eta = " - "
        else:
            # limiting display to 99 hour 60 minutes
            eta_calcwith = self.printing_eta if self.printing_eta < 360000 else 360000 - 1
            eta_hours = eta_calcwith // 3600
            eta_minutes = ( eta_calcwith - ( eta_hours * 3600 ) ) // 60
            visible_eta = "%02d:%02d" % ( eta_hours, eta_minutes )

        screen, screen_width, screen_height = self.ensure_screen('OctPriSCR1')
        if screen and 'TextETA' in screen.widgets:
            self._logger.info("LCDd 'TextETA' == '%s'" % visible_eta )
            screen.widgets['TextETA'].set_text( visible_eta )
            screen.widgets['TextETA'].update()

    def update_screen_TextFIN( self ):
        if self.printing_eta is None or self.start_timestamp is None:
            visible_fin = " - "
        else:
            FINISH_DATETIME = datetime.now() + timedelta( seconds = self.printing_eta )
            START_DATE = self.start_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            FIN_DATE = FINISH_DATETIME.replace(hour=0, minute=0, second=0, microsecond=0)

            if ( (FIN_DATE-START_DATE).days == 0 ):
                visible_fin = "%02d:%02d" % ( FINISH_DATETIME.hour, FINISH_DATETIME.minute )
            else:
                visible_fin = "+%dd %02d:%02d" % ( (FIN_DATE-START_DATE).days, FINISH_DATETIME.hour, FINISH_DATETIME.minute )

        screen, screen_width, screen_height = self.ensure_screen('OctPriSCR1')
        if screen and 'TextFIN' in screen.widgets:
            self._logger.info("LCDd 'TextFIN' == '%s'" % visible_fin )
            screen.widgets['TextFIN'].set_text( visible_fin )
            screen.widgets['TextFIN'].set_x( screen_width - len( visible_fin ) )
            screen.widgets['TextFIN'].update()


    def on_print_progress(self, storage, path, progress ):
        self.printing_percent = progress

        self.update_screen_TextPercent()

    def on_timer_seconds(self):
        try:
            self.printing_eta = self._printer.get_current_data()['progress']['printTimeLeft']
        except:
            self.printing_eta = None

        self.update_screen_TextPercent()
        self.update_screen_TextETA()
        self.update_screen_TextFIN()

    def on_timer_screen(self):
        self.timer_screen = None
        self.screen_priority_state = STATE_IDLE
        self.update_screen_priority()

    def initialize_lcd(self):
        if not self._settings.get_boolean(["enabled"]):
            self.lcd = None
            self._logger.info("Connection to LCDd are disabled")
            return False

        try:
            self.lcd = Server(hostname=self._settings.get(["host"]), port=self._settings.get_int(["port"]), debug=False)
            self.lcd.start_session()
        except:
            self.lcd = None
            self._logger.info("Unable to establish the connection to the LCDd")
            return False

        self.lcd.add_screen("OctPriSCR1")

        if self._settings.get_boolean(["title_show"]):
            first_linenum = 2
            self.lcd.screens['OctPriSCR1'].add_title_widget("TitleText", text = self._settings.get(["title_text"]) )
            self.lcd.screens['OctPriSCR1'].set_heartbeat("on")
        else:
            first_linenum = 1
            self.lcd.screens['OctPriSCR1'].set_heartbeat("off")

        self.update_screen_priority()

        self.lcd.screens['OctPriSCR1'].add_string_widget("TextPercent", text="", y= first_linenum+0, x=self.lcd.server_info['screen_width']-3 )
        self.lcd.screens['OctPriSCR1'].add_scroller_widget("TextFileName", text="", speed=5, left=1, top=first_linenum+0, right=self.lcd.server_info['screen_width']-5, bottom=first_linenum+0 )
        self.lcd.screens['OctPriSCR1'].add_string_widget("TextETA", text="", y=first_linenum+1,x=2,)
        self.lcd.screens['OctPriSCR1'].add_string_widget("TextFIN", text="", y=first_linenum+1,x=self.lcd.server_info['screen_width']-2)
        self.lcd.screens['OctPriSCR1'].add_icon_widget("IconETA", x=1, y=first_linenum+1, name="SELECTOR_AT_RIGHT" )
        self.lcd.screens['OctPriSCR1'].add_icon_widget("IconFIN", x=self.lcd.server_info['screen_width'], y=first_linenum+1, name="SELECTOR_AT_LEFT" )

        self._logger.info("LCDd connection established")

        self.update_screen_TextFileName()
        self.update_screen_TextPercent()
        self.update_screen_TextETA()
        self.update_screen_TextFIN()

        return True

    def ensure_screen(self, ref):
        if not self.lcd or not self.lcd.alive_session():
            if not self.initialize_lcd():
                return ( None, None, None )

        if self.lcd and self.lcd.alive_session() and ref in self.lcd.screens:
            return ( self.lcd.screens[ref], self.lcd.server_info['screen_width'], self.lcd.server_info['screen_height'] )

        return ( None, None, None )

__plugin_name__ = "LCDproc"

# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
__plugin_pythoncompat__ = ">=3.4,<4"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = LcdprocPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
