# Yosys black box synthesis test case suite
#
# Test case to create simple RAM with different configurations
#
# Currently, tests only for simulation output. Co-Simulation and
# synthesis tests performed later on
#

import myhdl
from myhdl import *

from .cosim_common import *

import sys
sys.path.append("../../../../synthesis/yosys/")

import ram

from myhdl.conversion import yshelper


def test_convert_memory_ce():
	"Test memory with CE signal"
	a, b = [ ram.DPport(8, 8) for i in range(2) ]
	
	ram_inst_ce = ram.dpram_r1w1(a, b, None, True)

	design = yshelper.Design("test_ce")

	ram_inst_ce.convert("yosys_module", design, name="ram_inst_ce", trace=False)

	# design.display_dir()
	design.display_rtl()

def test_convert_memory():
	"Test memory without CE signal"
	a, b = [ ram.DPport(8, 8) for i in range(2) ]
	
	ram_inst = ram.dpram_r1w1(a, b, None, False)

	design = yshelper.Design("test")

	ram_inst.convert("yosys_module", design, name="ram_inst", trace=False)

	# design.display_dir()
	design.display_rtl()

