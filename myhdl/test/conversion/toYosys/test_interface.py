# Interface tests
#

from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
import pytest

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

# TODO: HLS Class cases

UUT_LIST = [ const_intbv_argument, const_num_argument, const_dummy_argument ]

@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

