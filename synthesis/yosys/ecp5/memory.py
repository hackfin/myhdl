# Memory elements ECP5
#
# (c) 2020 <hackfin@section5.ch>
#
#

from myhdl import *
from myhdl.conversion import yshelper
from synthesis.yosys.autowrap import autowrap_unroll, unroll_bulk

@autowrap_unroll(unroll_bulk)
def DP16KD(DIA, ADA, CEA, OCEA, CLKA, WEA, CSA, RSTA, \
           DIB, ADB, CEB, OCEB, CLKB, WEB, CSB, RSTB, \
           DOA, DOB, **parameters):

	"""ECP5 true dual port RAM primitive"""

	if len(DIA) != 18: raise ValueError("Bad size")	
	if len(ADA) != 14: raise ValueError("Bad size")	
	if len(CSA) != 3: raise ValueError("Bad size")	
	if len(DIB) != 18: raise ValueError("Bad size")	
	if len(ADB) != 14: raise ValueError("Bad size")	
	if len(CSB) != 3: raise ValueError("Bad size")	
	if len(DOA) != 18: raise ValueError("Bad size")	
	if len(DOB) != 18: raise ValueError("Bad size")	

	doa = Signal(intbv()[18:])
	dob = Signal(intbv()[18:])

	@always_comb
	def assign():
		DOA.next = doa
		DOB.next = dob
		raise SystemError("Simulation model missing")

	return assign


@autowrap_unroll(unroll_bulk)
def PDPW16KD(DI, ADW, BE, CEW, CLKW, CSW, ADR, CER, OCER, CLKR, CSR, RST, \
   DO, **parameter):

	"""ECP5 Pseudo dual port RAM primitive"""

	if len(DI) != 36: raise ValueError("Bad size")	
	if len(ADW) != 14: raise ValueError("Bad size")	
	if len(BE) != 4: raise ValueError("Bad size")	
	if len(CSW) != 3: raise ValueError("Bad size")	
	if len(ADR) != 14: raise ValueError("Bad size")	
	if len(CSR) != 3: raise ValueError("Bad size")	
	if len(DO) != 36: raise ValueError("Bad size")	

	do = Signal(intbv()[36:])

	@always_comb
	def assign():
		DO.next = do
		raise SystemError("Simulation model missing")

	return assign

@autowrap_unroll(unroll_bulk)
def DPR16X4C(DI, WAD, WCK, WRE, RAD, DO, **parameters):

	"""ECP5 distributed pseudo dual port RAM primitive"""

	if len(DI) != 4 : raise ValueError("Bad size")	
	if len(WAD) != 4 : raise ValueError("Bad size")	
	if len(RAD) != 4 : raise ValueError("Bad size")	

	do = Signal(intbv()[4:])

	@always_comb
	def assign():
		DO.next = do
		raise SystemError("Simulation model missing")

	return assign

@autowrap_unroll(unroll_bulk)
def SPR16X4C(DI, AD, CK, WRE, DO, **parameters):

	"""ECP5 distributed single port RAM primitive"""

	if len(DI) != 4 : raise ValueError("Bad size")	
	if len(WA) != 4 : raise ValueError("Bad size")	

	do = Signal(intbv()[4:])

	@always_comb
	def assign():
		DO.next = do
		raise SystemError("Simulation model missing")

	return assign

