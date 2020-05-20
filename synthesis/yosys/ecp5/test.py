import sys
sys.path.append("../../../")

from myhdl import *
from myhdl.conversion import yshelper

from components import EHXPLLL, JTAGG

CLK_25MHZ_CONFIG = {
    "PLLRST_ENA"       : "DISABLED",
    "INTFB_WAKE"       : "DISABLED",
    "STDBY_ENABLE"     : "DISABLED",
    "DPHASE_SOURCE"    : "DISABLED",
    "OUTDIVIDER_MUXA"  : "DIVA",
    "OUTDIVIDER_MUXB"  : "DIVB",
    "OUTDIVIDER_MUXC"  : "DIVC",
    "OUTDIVIDER_MUXD"  : "DIVD",
    "CLKI_DIV"         : 4,
    "CLKOP_ENABLE"     : "ENABLED",
    "CLKOP_DIV"        : 6,
    "CLKOP_CPHASE"     : 5,
    "CLKOP_FPHASE"     : 0,
    "CLKOP_TRIM_DELAY" : 0,
    "CLKOP_TRIM_POL"   : "FALLING",
    "CLKOS_ENABLE"     : "ENABLED",
    "CLKOS_DIV"        : 30,
    "CLKOS_CPHASE"     : 29,
    "CLKOS_FPHASE"     : 0,
    "CLKOS_TRIM_DELAY" : 0,
    "CLKOS_TRIM_POL"   : "FALLING",
    "CLKOS2_ENABLE"    : "ENABLED",
    "CLKOS2_DIV"       : 15,
    "CLKOS2_CPHASE"    : 14,
    "CLKOS2_FPHASE"    : 0,
    "CLKOS3_ENABLE"    : "ENABLED",
    "CLKOS3_DIV"       : 10,
    "CLKOS3_CPHASE"    : 9,
    "CLKOS3_FPHASE"    : 0,
    "FEEDBK_PATH"      : "CLKOP",
    "CLKFB_DIV"        : 5
}

class JtagPort:
	def __init__(self):
		self.tck = Signal(bool())
		self.tms = Signal(bool())
		self.tdi = Signal(bool())
		self.tdo = Signal(bool())

@block
def pll(clki, clkop, clkos, jtag):

	parameters = CLK_25MHZ_CONFIG

	fb, os, os2, os3, lock, intlock = [ Signal(bool()) for i in range(6) ]
	refclk, clkintfb = [ Signal(bool()) for i in range(2) ]

	e = EHXPLLL(clki, fb, False, False, False, False, \
	False, False, \
	False, False, False, True, False, False, \
	clkop, os, os2, os3, lock, intlock, \
	refclk, clkintfb, \
	**parameters)

	jtdo1, jtdo2, jtdi, jtck, jrti1, jrti2, \
		jshift, jupdate, jrstn, \
		jce1, jce2 = [ Signal(bool()) for i in range(11) ]

	j = JTAGG(jtag.tck, jtag.tms, jtag.tdi, jtag.tdo, \
		jtdo1, jtdo2, jtdi, jtck, jrti1, jrti2, \
		jshift, jupdate, jrstn, jce1, jce2, ER1 = "ENABLED")

	@always_comb
	def assign():
		fb.next = os
		clkos.next = os

	return instances()

def synth(design):
	TECHLIBS_PATH = "/media/sandbox/usr/share/yosys"
	YOSYS_ABC_EXE = "/media/sandbox/usr/bin/yosys-abc"

	# add_builtins(design)

	# commands = [ "hierarchy -check"]
	commands = [ "proc", "flatten", "tribuf -logic", "deminout", "opt_expr", "debug opt_clean"]
	# commands += [ "stat"]
	commands += [ "check", "opt", "wreduce", "peepopt", "opt_clean", "share"]
	commands += [ "techmap -map %s/cmp2lut.v -D LUT_WIDTH=4" % TECHLIBS_PATH ]
	commands += [ "opt_expr", "opt_clean" ]
	commands += [ "opt", "fsm", "opt -fast", "memory -nomap", "opt_clean"]

	commands += [ "dffsr2dff; dff2dffs; opt_clean" ]
	commands += [ "dff2dffe -direct-match $_DFF_* -direct-match $__DFFS_*" ]
	commands += [ "techmap -D NO_LUT -map %s/ecp5/cells_map.v" % TECHLIBS_PATH ]
	commands += [ "opt_expr -undriven -mux_undef; simplemap; ecp5_ffinit" ]
	commands += [ "ecp5_gsr", "attrmvcp -copy -attr syn_useioff"]
	commands += [ "abc -exe %s" % YOSYS_ABC_EXE ]
	commands += [ "techmap -map %s/ecp5/latches_map.v" % TECHLIBS_PATH ]
	commands += [ "abc -exe %s -lut 4:7 -dress" % YOSYS_ABC_EXE ]
	commands += [ "clean" ]
	commands += [ "opt_lut_ins -tech ecp5", "clean" ]
	commands += [ "autoname", "hierarchy -check", "stat", "check -noinit" ]

	for c in commands:
		design.run(c)

d = yshelper.Design("pll")
# d.run("read_verilog /tmp/test.v")

# m = d.get().addModule(yshelper.ID("$GNA"))
# print(dir(m))

if 1:
	clki = Signal(bool())

	clkop, clkos = [ Signal(bool()) for i in range(2) ]

	jtag = JtagPort()

	p = pll(clki, clkop, clkos, jtag)
	p.convert("yosys_module", d)

	d.finalize()


	dn = d.get()

	for n, m in dn.modules_.items():
		print("==== %s ====" % n)
		for p in m.avail_parameters:
			print("PARAM:", p)

	#	m.avail_parameters.append(yshelper.PID("GNA"))

	d.write_verilog("pll")
	d.run("write_ilang test.il")
	d.run("show -prefix pre -format ps")
	# z = input("HIT RETURN FOR SYNTH")
	synth(d)
	d.run("show -prefix post -format ps")


