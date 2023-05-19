import os
import logging
import configparser

class Config:
    def __init__(self, path):
        self.info = dict()
        self.path = path

    def getInfo(self):
        #TODO Описание функции
        self._checkConfig()
        config = configparser.ConfigParser()
        config.read(self.path)
        #TODO log
        
        for i in FIELDS:
            self.info[i] = config.get("Settings", i)
        #TODO log
        return self.info


    def _createConfig(self):
        """
        Create a config file with fields via constant
        """
        #TODO log
        config = configparser.ConfigParser()
        config.add_section("Settings")
        for field in FIELDS:
            if field in self.info:
                config.set("Settings", field, self.info[field] if type(self.info[field]) != list else "".join(self.info[field]))
            else:
                config.set("Settings", field, "")
        

        with open(self.path, "w") as config_file:
            config.write(config_file)
        #TODO log
        raise Exception("ConfigError: the configuration file is empty. Please fill in all the fields in it")


    def _checkConfig(self):
        """
        Verification of the configuration file
        """
        if not os.path.exists(self.path):
            self._createConfig()

        config = configparser.ConfigParser()
        config.read(self.path)
        
        for i in FIELDS:
            if not i in config["Settings"]:
                #TODO log
                self._createConfig()
                break
            elif config["Settings"][i] == "":
                #TODO log
                raise Exception("ConfigError: the configuration file is empty. Please fill in all the fields in it")
            self.info[i] = config.get("Settings", i)
        #TODO log

SRC_PATH = os.path.dirname(os.path.realpath(__file__))
FIELDS = ["token", "admins", "skip_updates", "parse_mode", "handlers_dir", "models_dir", "context_file", "handlers", "cover_rz_name", "cover_ps_name", "localserver"]
SETTINGS = Config(f"{SRC_PATH}/settings.ini").getInfo()

TOKEN = SETTINGS["token"]
ADMINS = SETTINGS["admins"].split(",")
SKIP_UPDATES = False if SETTINGS["skip_updates"].lower() == "false" else True
PARSE_MODE = None if SETTINGS["parse_mode"].lower() == "none" else SETTINGS["parse_mode"]
LOCALSERVER = True if SETTINGS["localserver"].lower() == "true" else False
CONTEXT_FILE = SETTINGS["context_file"]

#TODO PROXY
#TODO PROXY_AUTH
HANDLERS = SETTINGS["handlers"].split(",")

FILES_PATH = f"{SRC_PATH}/files"
PODCAST = f"{FILES_PATH}/podcast.mp3"
HANDLERS_DIR = f'{SRC_PATH}/{SETTINGS["handlers_dir"]}'
HANDLERS_NAME = SETTINGS["handlers_dir"]
MODELS_DIR = f'{SRC_PATH}/{SETTINGS["models_dir"]}'
MODELS_NAME = SETTINGS["models_dir"]
COVER_RZ_PATH = f'{FILES_PATH}/{SETTINGS["cover_rz_name"]}'
COVER_PS_PATH = f'{FILES_PATH}/{SETTINGS["cover_ps_name"]}'