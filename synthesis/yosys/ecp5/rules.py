# ECP5 yosys inference/mapping default rules
#
# (c) 2020 section5.ch
#

from myhdl.conversion import yshelper

TECHLIBS_PATH = "/usr/share/yosys"
YOSYS_ABC_EXE = "/usr/bin/yosys-abc"

class SynthesisRulesECP5(yshelper.YosysInferenceRule):
	"Default ECP5 synthesis/mapping rule class"
	def __init__(self, tl = TECHLIBS_PATH, abc = YOSYS_ABC_EXE):
		self.techlibs = tl
		self.abc = abc

	def map(self, design, **kwargs):
		"""This command is called by the `design.map()` mapper pass, if this mapper
was registered to the design."""

		t = self.techlibs

		commands = [ "read_verilog -lib -specify %s/ecp5/cells_sim.v %s/ecp5/cells_bb.v" % (t, t) ]

		commands += [ "hierarchy -check"]
		commands += [ "proc", "flatten", "tribuf -logic", "deminout", "opt_expr", "debug opt_clean"]
		commands += [ "check", "opt", "wreduce", "peepopt", "opt_clean", "share"]
		commands += [ "techmap -map %s/cmp2lut.v -D LUT_WIDTH=4" % t ]
		commands += [ "opt_expr", "opt_clean" ]
		commands += [ "opt", "fsm", "opt -fast", "memory -nomap", "opt_clean"]
		commands += [ "memory_bram -rules %s/ecp5/brams.txt"  % t, "techmap -map %s/ecp5/lutrams_map.v" % t ]
		commands += [ "memory_bram -rules %s/ecp5/lutrams.txt"  % t, "techmap -map %s/ecp5/lutrams_map.v" % t ]
		commands += [ "techmap -map %s/techmap.v -map %s/ecp5/arith_map.v" % (t, t) ]

		commands += [ "dff2dffs; opt_clean" ]
		commands += [ "dff2dffe -direct-match $_DFF_* -direct-match $_SDFF_*" ]
		commands += [ "techmap -map %s/ecp5/cells_map.v" % t ]
		commands += [ "opt_expr -undriven -mux_undef" ]
		commands += [ "simplemap; ecp5_ffinit" ]
		commands += [ "ecp5_gsr", "attrmvcp -copy -attr syn_useioff" ]
		commands += [ "abc -exe %s" % self.abc ]
		commands += [ "techmap -map %s/ecp5/latches_map.v" % t ]
		commands += [ "abc -exe %s -lut 4:7 -dress" % self.abc ]
		commands += [ "clean" ]
		commands += [ "techmap -map %s/ecp5/cells_map.v" % t ]
		commands += [ "opt_lut_ins -tech ecp5", "clean" ]
		commands += [ "autoname", "hierarchy -check", "stat", "check -noinit" ]
		design.run(commands)

