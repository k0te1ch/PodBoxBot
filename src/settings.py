import os
import configparser

class Config:
    def __init__(self):
        self.info = dict()

    def getInfo(self):
        self._checkConfig()
        config = configparser.ConfigParser()
        config.read(PATH)
        
        for i in FIELDS:
            self.info[i] = config.get("Settings", i)
        return self.info


    def _createConfig(self):
        """
        Create a config file with fields via constant
        """
        config = configparser.ConfigParser()
        config.add_section("Settings")
        for field in FIELDS:
            config.set("Settings", field, "")
        
        with open(PATH, "w") as config_file:
            config.write(config_file)


    def _checkConfig(self):
        """
        Verification of the configuration file
        """
        if not os.path.exists(PATH):
            self._createConfig()

        config = configparser.ConfigParser()
        config.read(PATH)
        
        for i in FIELDS:
            if not i in config["Settings"]:
                self._createConfig()
                break

PATH = "Settings.ini"
FIELDS = ["token", "font", "font_size", "font_info"]
SETTINGS = Config().getInfo()