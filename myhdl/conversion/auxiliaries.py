def dump_hierarchy(hierarchy, func, outfile = "/tmp/hdump.txt"):
	f = open(outfile, "w")
	# f = sys.stdout
	l = 0
	print("  Arguments:", file=f)
	for argname, arg in func.argdict.items():
		print("    '%s' : %030s(%s)" % (argname, _TYPE(arg), arg._type.__name__), file=f)

	print("  Symbols:", file=f)
	for argname, arg in func.symdict.items():
		if isinstance(arg, str):
			print("    '%s' : '%s'" % (argname, arg), file=f)
		elif isinstance(arg, _Signal):
			print("    SIGNAL '%s' : %030s(%s)" % (argname, _TYPE(arg), arg._type.__name__), file=f)

	print(60 * "=")
	print("TOP level module '%s'" % hierarchy.top.name)

	for inst in hierarchy.hierarchy:
		print("Module: '%s'" % inst.name, file=f)

		print(60 * "=")
		print("  Arg:", file=f)
		for argname, arg in inst.obj.symdict.items():
			if isinstance(arg, str):
				print("    '%s' : '%s'" % (argname, arg), file=f)
			elif isinstance(arg, _Signal):
				print("    SIGNAL '%s' : %030s(%s)" % (argname, _TYPE(arg), arg._type.__name__), file=f)

		print(60 * "=")

		print("  Signals:", file=f)
		for signame, sig in inst.sigdict.items():
			print("    '%s' : %030s(%s)" % (signame, _TYPE(sig), sig._type.__name__), file=f)


		print("  Processes:", file=f)
		l = []
		for i in inst.subs:
			if isinstance(i[1], _Block):
				print("    '%s' : %s" % (i[0], _TYPE(i[1])), file=f)
			else:
				print("    '%s' : %s" % (i[0], _TYPE(i[1])), file=f)
				l.append(i[1])

