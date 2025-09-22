# Make helpers for managing Quantum Commander via qcctl

.PHONY: qstart qstop qrestart qstatus qlogs qlog qhealth qopen qenable qdisable

qstart:
	./bin/qcctl start

qstop:
	./bin/qcctl stop

qrestart:
	./bin/qcctl restart

qstatus:
	./bin/qcctl status

qlogs:
	./bin/qcctl logs

qlog:
	./bin/qcctl log

qhealth:
	./bin/qcctl health

qopen:
	./bin/qcctl open

qenable:
	./bin/qcctl enable

qdisable:
	./bin/qcctl disable

