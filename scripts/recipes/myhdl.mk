MYHDL_UPSTREAM = $(HOME)/src/myhdl/myhdl-yosys

all: install

$(MYHDL_UPSTREAM):
#	[ -e $(dir $@) ] || install -d $(dir $@)
#	cd $(dir $@) && \
#	git clone -b jupyosys https://github.com/hackfin/myhdl $(notdir $@)


install: $(MYHDL_UPSTREAM)
	$(MAKE) -C $(MYHDL_UPSTREAM)/cosimulation/icarus all
	cd $< && python3 setup.py install --user

# Run those tests that should pass by default:
test:
	$(MAKE) -C $(MYHDL_UPSTREAM)/myhdl/test/conversion/toYosys

fulltest:
	# The general test will currently fail.
	cd $(MYHDL_UPSTREAM)/myhdl/test/conversion && $(MAKE) all

.PHONY: install test
