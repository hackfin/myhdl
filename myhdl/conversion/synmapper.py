
SM_NUM, SM_BOOL, SM_STRING, SM_WIRE, SM_RECORD, SM_VAR, SM_MEMPORT, SM_ARRAY = range(8)

class SynthesisMapper:
	def __init__(self, el_type, is_signed = False):
		self.el_type = el_type
		self.q = None
		self.trunc = False # True when truncation allowed
		self.is_signed = is_signed

	def isConst(self):
		return self.el_type == SM_NUM

	def __repr__(self):
		types = [ "NUM", "BOOL", "STRING", "WIRE", "RECORD", "VAR", "MEMPORT" ]
		if self.q:
			identifier = "$"
		else:
			identifier = "X"
		return "[%s: %s]" % (types[self.el_type], identifier)

