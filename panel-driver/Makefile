obj-m += panel-himax-hx83121a.o
obj-m += gaokun-overlay-loader.o

KDIR := /home/lewis-server/linux-6.18/linux-6.18.8

all: gaokun_panel_dtbo.h
	make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -C $(KDIR) M=$(PWD) modules

gaokun_panel_dtbo.h: gaokun-panel.dtbo
	xxd -i gaokun-panel.dtbo > gaokun_panel_dtbo.h

gaokun-panel.dtbo: gaokun-panel-overlay-v4.dts
	dtc -@ -I dts -O dtb -o gaokun-panel.dtbo gaokun-panel-overlay-v4.dts

clean:
	make -C $(KDIR) M=$(PWD) clean
	rm -f gaokun-panel.dtbo gaokun_panel_dtbo.h
