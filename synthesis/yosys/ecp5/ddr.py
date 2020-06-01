from myhdl import *
from myhdl.conversion import yshelper
from synthesis.yosys.autowrap import autowrap_unroll, unroll_bulk

@autowrap_unroll(unroll_bulk)
def DDRDLLA(D, SCLK, RST, Q,
	CLK, UDDCNTLN, FREEZE, \
	DDRDEL, LOCK, \
	DCNTL, **parameter):

	q = Signal(intbv()[2:])
	lock = Signal(bool())
	ddrdel = Signal(bool())

	@always_comb
	def dummy():
		LOCK.next = lock
		DCNTL.next = d
		DDRDEL.next = d
		raise SystemError("Simulation model missing")
	return dummy

@autowrap_unroll(unroll_bulk)
def DQSBUFM(DQSI, READ, READCLKSEL, DDRDEL, ECLK, SCLK, RST,
	DYNDELAY, PAUSE, RDLOADN, RDMOVE, RDDIRECTION,
	WRLOADN, WRMOVE, WRDIRECTION,
	DQSR90, DQSW, DQSW270, RDPNTR, WRPNTR, DATAVALID,
	BURSTDET, RDCFLAG, WRCFLAG,
	**parameter):

	if len(READ) != 2: raise ValueError("Bad size")	
	if len(READCLKSEL) != 3: raise ValueError("Bad size")	
	if len(DYNDELAY) != 8: raise ValueError("Bad size")	

	dqsr90, dqsw, dqsw270, datavalid, burstdet, rdcflag, wrcflag = \
	[ Signal(bool()) for i in range(7) ]
	rdpntr, wrpntr = [ Signal(intbv()[3:]) for i in range(2) ]

	@always_comb
	def dummy():
		DQSR90.next = dqsr90
		DQSW.next = dqsw
		DQSW270.next = dqsw270
		RDPNTR.next = rdpntr
		WRPNTR.next = wrpntr
		DATAVALID.next = datavalid
		BURSTDET.next = burstdet
		RDCFLAG.next = rdcflag
		WRCFLAG.next = wrcflag

		raise SystemError("Simulation model missing")
	return dummy


@autowrap_unroll(unroll_bulk)
def IDDRX1F(D, SCLK, RST, Q, **parameter):

	q = Signal(intbv()[2:])

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def IDDRX2F(D, SCLK, ECLK, RST, ALIGNWD, Q, **parameter):

	q = Signal(intbv()[4:])

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def IDDR71B(D, SCLK, ECLK, RST, ALIGNWD, Q, **parameter):
	q = Signal(intbv()[7:])

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy


@autowrap_unroll(unroll_bulk)
def ODDRX1F(D, SCLK, RST, Q, **parameter):

	q = Signal(bool())

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def ODDRX2F(D, SCLK, ECLK, RST, ALIGNWD, Q, **parameter):

	q = Signal(bool())

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def ODDR71B(D, SCLK, ECLK, RST, ALIGNWD, Q, **parameter):

	q = Signal(bool())

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy


@autowrap_unroll(unroll_bulk)
def IDDRX2DQA(SCLK, ECLK, DQSR90, D, RST, RDPNTR, WRPNTR, \
	Q, QWL, **parameter):

	q = Signal(intbv()[4:])

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def ODDRX2DQA(D, DQSW270, SCLK, ECLK, RST, \
	Q, **parameter):

	q = Signal(intbv()[4:])

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy

@autowrap_unroll(unroll_bulk)
def ODDRX2DQSB(D, SCLK, ECLK, DQSW, RST, Q):

	q = Signal(bool())

	@always_comb
	def dummy():
		Q.next = q
		raise SystemError("Simulation model missing")

	return dummy
