# Interface tests
#

from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8

@block
def const_intbv_argument(clk, ce, reset, dout, debug):
	"Test case with constant immediate passed as parameter"
	imm = intbv(12)[8:]
	inst_lfsr2 = lfsr8(clk, ce, reset, imm, dout)
	return instances()

@block
def const_num_argument(clk, ce, reset, dout, debug):
	"Test case with constant immediate passed as parameter"
	imm = 12
	inst_lfsr2 = lfsr8(clk, ce, reset, imm, dout)
	return instances()

@block
def const_dummy_argument(clk, ce, reset, dout, debug, test = None):
	"Test case with superfluous argument"
	imm = 12
	inst_lfsr2 = lfsr8(clk, ce, reset, imm, dout)
	return instances()


def test_const_intbv_argument():
	UNIT = const_intbv_argument
	arst = False
	run_conversion(UNIT, arst, None, True) # No wrapper, display
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

def test_const_num_argument():
	UNIT = const_num_argument
	arst = False
	run_conversion(UNIT, arst, None, True) # No wrapper, display
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

def test_const_dummy_argument():
	UNIT = const_dummy_argument
	arst = False
	run_conversion(UNIT, arst, None, False) # No wrapper, display
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

