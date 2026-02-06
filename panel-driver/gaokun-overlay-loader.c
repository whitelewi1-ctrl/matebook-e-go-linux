// SPDX-License-Identifier: GPL-2.0
/*
 * Huawei MateBook E Go Panel Overlay Loader
 *
 * This module loads a device tree overlay to add the panel node
 * that is missing from the UEFI-provided DTB.
 *
 * The overlay is embedded directly in the module since request_firmware()
 * is not available during early boot.
 */

#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_fdt.h>

/* Embedded overlay data - generated from gaokun-panel.dtbo */
#include "gaokun_panel_dtbo.h"

static int ovcs_id = -1;

static int __init gaokun_overlay_init(void)
{
	int ret;
	struct device_node *panel_node;

	pr_info("gaokun_overlay: initializing overlay loader\n");

	/* Check if panel already exists */
	panel_node = of_find_node_by_path("/soc@0/display-subsystem@ae00000/dsi@ae94000/panel@0");
	if (panel_node) {
		pr_info("gaokun_overlay: panel@0 already exists, skipping\n");
		of_node_put(panel_node);
		return 0;
	}

	pr_info("gaokun_overlay: applying overlay (%u bytes)\n", gaokun_panel_dtbo_len);

	ret = of_overlay_fdt_apply(gaokun_panel_dtbo, gaokun_panel_dtbo_len, &ovcs_id, NULL);
	if (ret) {
		pr_err("gaokun_overlay: failed to apply overlay: %d\n", ret);
		return ret;
	}

	pr_info("gaokun_overlay: overlay applied successfully (ovcs_id=%d)\n", ovcs_id);

	/* Verify the panel node was created */
	panel_node = of_find_node_by_path("/soc@0/display-subsystem@ae00000/dsi@ae94000/panel@0");
	if (panel_node) {
		pr_info("gaokun_overlay: panel@0 node created successfully\n");
		of_node_put(panel_node);
	} else {
		pr_warn("gaokun_overlay: panel@0 node not found after overlay!\n");
	}

	return 0;
}

static void __exit gaokun_overlay_exit(void)
{
	if (ovcs_id >= 0) {
		of_overlay_remove(&ovcs_id);
		pr_info("gaokun_overlay: overlay removed\n");
	}
}

module_init(gaokun_overlay_init);
module_exit(gaokun_overlay_exit);

MODULE_DESCRIPTION("Panel overlay loader for Huawei MateBook E Go");
MODULE_AUTHOR("Lewis");
MODULE_LICENSE("GPL");
