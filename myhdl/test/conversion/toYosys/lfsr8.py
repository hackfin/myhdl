import sys
from myhdl import *

@block
def lfsr8a(clk, ce, reset, rval, dout):
	"""Has 252 states only"""
	v = Signal(modbv(rval)[8:])

	@always_seq(clk.posedge, reset)
	def worker():
		if enable == 1:
			b = bool(not v[7])
			b = bool(b ^ (v[6] ^ v[4]))
			w = concat(v[7:], b)
			v.next = w

	@always_comb
	def assign():
		dout.next = v
	
	return instances()

@block
def lfsr8(clk, ce, reset, rval, dout):
	"""LFSR with all states"""
	v = Signal(modbv(rval)[8:])
	fb = Signal(bool())

	@always_seq(clk.posedge, reset)
	def worker():
		if ce == 1:
			v.next = concat(v[6], v[5], v[4], v[3] ^ fb, v[2] ^ fb, v[1] ^ fb, v[0], fb)

	@always_comb
	def assign():
		e = v[7:0] == 0
		fb.next = v[7] ^ e
		dout.next = v

	return instances()

@block
def tb_lfsr():
	enable = Signal(bool(0))
	reset = ResetSignal(0, 1, False)
	clk = Signal(bool(0))
	dout = Signal(intbv()[8:])
	cnt = Signal(intbv()[10:])
	uut = lfsr8(clk, enable, reset, 0, dout)

	@always(delay(50))
	def clkgen():
		clk.next = not clk

	@always(clk.posedge)
	def count():
		# print("0x%02x," % (dout), end=''),
		if enable == 1:
			if int(cnt) % 8 == 0:
				print()
			cnt.next = cnt + 1


	@instance
	def start():
		enable.next = 0
		reset.next = 1
		yield delay(10)
		reset.next = 0
		yield delay(10)
		enable.next = 1

	return instances()


def simulate():
	tb = traceSignals(tb_lfsr)
	sim = Simulation(tb)
	sim.run(100000)


if __name__ == "__main__":

	if len(sys.argv) > 1 and sys.argv[1] == '-s':
		simulate()
	else:
		enable = Signal(bool(0))
		reset = ResetSignal(0, 1, False)
		clk = Signal(bool(0))
		dout = Signal(intbv()[8:])

		lfsr = lfsr8(clk, reset, 0, enable, dout)
		lfsr.convert("VHDL")
