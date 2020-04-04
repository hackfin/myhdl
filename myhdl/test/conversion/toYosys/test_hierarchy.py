from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8

@block
def lfsr8_multi(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])
	lq1, lq2, lq3 = [ Signal(modbv(0)[8:]) for i in range(3) ]

	inst_lfsr2 = lfsr8(clk, 1, reset, 2, lq1)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, lq2)

	inst_lfsr_ce = lfsr8(clk, ce, reset, 0, lq3)


	@always_seq(clk.posedge, reset)
	def assign():
		if counter % 3 == 0:
			dout.next = lq1
		elif counter % 3 == 1:
			dout.next = lq2
		else:
			dout.next = lq3

	return instances()

def test_lfsr():
	UNIT = lfsr8_multi
	arst = False
	run_conversion(UNIT, arst, None, True)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)


