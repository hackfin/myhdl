REDBG = "\033[7;31m"
VIOBG = "\033[7;35m"
BLUEBG = "\033[7;34m"
GREEN = "\033[32m"
OFF = "\033[0m"

import inspect

def lineno():
	return inspect.currentframe().f_back.f_lineno

ENABLE_DEBUG = False

