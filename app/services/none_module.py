from loguru import logger


class _NotDefinedModule(Exception):
    pass


class _NoneModule:

    def __init__(self, module_name, attr_name) -> None:
        self.module_name = module_name
        self.attr_name = attr_name

    def __getitem__(self, item) -> _NotDefinedModule:
        msg = f"You are using {self.module_name} while the {self.attr_name} is not set in config"
        logger.critical(msg)
        raise _NotDefinedModule(msg)

    def __getattr__(self, attr) -> _NotDefinedModule:
        msg = f"You are using {self.module_name} while the {self.attr_name} is not set in config"
        logger.critical(msg)
        raise _NotDefinedModule(msg)
