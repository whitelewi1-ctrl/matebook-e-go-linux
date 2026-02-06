#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>

#define DPU_BASE    0xae01000
#define DSC0_BASE   (DPU_BASE + 0x80000)  /* dce_0_0 and dce_0_1 */
#define DSC0_ENC0   (DSC0_BASE + 0x100)   /* encoder sub-block 0 */
#define DSC0_ENC1   (DSC0_BASE + 0x200)   /* encoder sub-block 1 */
#define DSC0_CTL0   (DSC0_BASE + 0xF00)   /* ctl sub-block 0 */
#define DSC0_CTL1   (DSC0_BASE + 0xF80)   /* ctl sub-block 1 */

/* INTF_1 (DSI-0) and INTF_2 (DSI-1) */
#define INTF1_BASE  (DPU_BASE + 0x35000)
#define INTF2_BASE  (DPU_BASE + 0x36000)

/* INTF register offsets (from dpu_hw_intf.c) */
#define INTF_TIMING_ENGINE_EN   0x000
#define INTF_CONFIG             0x004
#define INTF_HSYNC_CTL          0x008
#define INTF_VSYNC_PERIOD_F0    0x00C
#define INTF_DISPLAY_V_START_F0 0x01C
#define INTF_DISPLAY_V_END_F0   0x024
#define INTF_ACTIVE_V_START_F0  0x02C
#define INTF_ACTIVE_V_END_F0    0x034
#define INTF_DISPLAY_HCTL       0x03C
#define INTF_ACTIVE_HCTL        0x040
#define INTF_POLARITY_CTL       0x050
#define INTF_CONFIG2            0x060
#define INTF_DISPLAY_DATA_HCTL  0x064
#define INTF_PANEL_FORMAT       0x090

/* PP_0 and PP_1 */
#define PP0_BASE    (DPU_BASE + 0x69000)
#define PP1_BASE    (DPU_BASE + 0x6a000)

/* CTL_0 */
#define CTL0_BASE   (DPU_BASE + 0x15000)

static volatile uint32_t *map_region(int fd, off_t phys_addr, size_t len) {
    off_t page = phys_addr & ~0xFFF;
    off_t offset = phys_addr - page;
    void *ptr = mmap(NULL, len + offset, PROT_READ, MAP_SHARED, fd, page);
    if (ptr == MAP_FAILED) { perror("mmap"); return NULL; }
    return (volatile uint32_t *)((char *)ptr + offset);
}

static uint32_t read_reg(int fd, off_t addr) {
    volatile uint32_t *p = map_region(fd, addr, 4);
    if (!p) return 0xDEADBEEF;
    uint32_t val = *p;
    munmap((void *)((uintptr_t)p & ~0xFFF), 0x1000);
    return val;
}

int main() {
    int fd = open("/dev/mem", O_RDONLY | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return 1; }

    printf("=== DPU DSC_0 Common (base 0x%x) ===\n", DSC0_BASE);
    printf("DSC_CMN_MAIN_CNF: 0x%08x\n", read_reg(fd, DSC0_BASE));

    printf("\n=== DSC_0 Encoder 0 (base 0x%x) ===\n", DSC0_ENC0);
    printf("ENC_DF_CTRL:      0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x00));
    printf("DSC_MAIN_CONF:    0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x30));
    printf("DSC_PICTURE_SIZE: 0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x34));
    printf("DSC_SLICE_SIZE:   0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x38));
    printf("DSC_MISC_SIZE:    0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x3C));
    printf("DSC_HRD_DELAYS:   0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x40));
    printf("DSC_RC_SCALE:     0x%08x\n", read_reg(fd, DSC0_ENC0 + 0x44));

    printf("\n=== DSC_0 CTL 0 (base 0x%x) ===\n", DSC0_CTL0);
    printf("DSC_CTL:          0x%08x\n", read_reg(fd, DSC0_CTL0 + 0x00));
    printf("DSC_CFG:          0x%08x\n", read_reg(fd, DSC0_CTL0 + 0x04));

    printf("\n=== DSC_0 Encoder 1 (base 0x%x) ===\n", DSC0_ENC1);
    printf("ENC_DF_CTRL:      0x%08x\n", read_reg(fd, DSC0_ENC1 + 0x00));
    printf("DSC_MAIN_CONF:    0x%08x\n", read_reg(fd, DSC0_ENC1 + 0x30));
    printf("DSC_PICTURE_SIZE: 0x%08x\n", read_reg(fd, DSC0_ENC1 + 0x34));
    printf("DSC_SLICE_SIZE:   0x%08x\n", read_reg(fd, DSC0_ENC1 + 0x38));

    printf("\n=== DSC_0 CTL 1 (base 0x%x) ===\n", DSC0_CTL1);
    printf("DSC_CTL:          0x%08x\n", read_reg(fd, DSC0_CTL1 + 0x00));
    printf("DSC_CFG:          0x%08x\n", read_reg(fd, DSC0_CTL1 + 0x04));

    printf("\n=== INTF_1 (DSI-0, base 0x%x) ===\n", INTF1_BASE);
    printf("TIMING_ENGINE_EN: 0x%08x\n", read_reg(fd, INTF1_BASE + INTF_TIMING_ENGINE_EN));
    printf("INTF_CONFIG:      0x%08x\n", read_reg(fd, INTF1_BASE + INTF_CONFIG));
    printf("HSYNC_CTL:        0x%08x\n", read_reg(fd, INTF1_BASE + INTF_HSYNC_CTL));
    printf("VSYNC_PERIOD_F0:  0x%08x\n", read_reg(fd, INTF1_BASE + INTF_VSYNC_PERIOD_F0));
    printf("DISP_V_START_F0:  0x%08x\n", read_reg(fd, INTF1_BASE + INTF_DISPLAY_V_START_F0));
    printf("DISP_V_END_F0:    0x%08x\n", read_reg(fd, INTF1_BASE + INTF_DISPLAY_V_END_F0));
    printf("ACTIVE_V_START:   0x%08x\n", read_reg(fd, INTF1_BASE + INTF_ACTIVE_V_START_F0));
    printf("ACTIVE_V_END:     0x%08x\n", read_reg(fd, INTF1_BASE + INTF_ACTIVE_V_END_F0));
    printf("DISPLAY_HCTL:     0x%08x\n", read_reg(fd, INTF1_BASE + INTF_DISPLAY_HCTL));
    printf("ACTIVE_HCTL:      0x%08x\n", read_reg(fd, INTF1_BASE + INTF_ACTIVE_HCTL));
    printf("POLARITY_CTL:     0x%08x\n", read_reg(fd, INTF1_BASE + INTF_POLARITY_CTL));
    printf("INTF_CONFIG2:     0x%08x\n", read_reg(fd, INTF1_BASE + INTF_CONFIG2));
    printf("DATA_HCTL:        0x%08x\n", read_reg(fd, INTF1_BASE + INTF_DISPLAY_DATA_HCTL));
    printf("PANEL_FORMAT:     0x%08x\n", read_reg(fd, INTF1_BASE + INTF_PANEL_FORMAT));

    printf("\n=== INTF_2 (DSI-1, base 0x%x) ===\n", INTF2_BASE);
    printf("TIMING_ENGINE_EN: 0x%08x\n", read_reg(fd, INTF2_BASE + INTF_TIMING_ENGINE_EN));
    printf("INTF_CONFIG:      0x%08x\n", read_reg(fd, INTF2_BASE + INTF_CONFIG));
    printf("HSYNC_CTL:        0x%08x\n", read_reg(fd, INTF2_BASE + INTF_HSYNC_CTL));
    printf("INTF_CONFIG2:     0x%08x\n", read_reg(fd, INTF2_BASE + INTF_CONFIG2));
    printf("DATA_HCTL:        0x%08x\n", read_reg(fd, INTF2_BASE + INTF_DISPLAY_DATA_HCTL));
    printf("DISPLAY_HCTL:     0x%08x\n", read_reg(fd, INTF2_BASE + INTF_DISPLAY_HCTL));

    /* Check pingpong DSC enable */
    printf("\n=== PP_0 (base 0x%x) ===\n", PP0_BASE);
    printf("PP_DSC_MODE:      0x%08x\n", read_reg(fd, PP0_BASE + 0x0));
    printf("PP_DSC_FLUSH:     0x%08x\n", read_reg(fd, PP0_BASE + 0x4));

    printf("\n=== PP_1 (base 0x%x) ===\n", PP1_BASE);
    printf("PP_DSC_MODE:      0x%08x\n", read_reg(fd, PP1_BASE + 0x0));
    printf("PP_DSC_FLUSH:     0x%08x\n", read_reg(fd, PP1_BASE + 0x4));

    /* DSI controller registers */
#define DSI0_BASE 0xae94000
#define DSI1_BASE 0xae96000

    printf("\n=== DSI-0 Controller (base 0x%x) ===\n", DSI0_BASE);
    printf("DSI_CTRL:         0x%08x\n", read_reg(fd, DSI0_BASE + 0x004));
    printf("DSI_STATUS:       0x%08x\n", read_reg(fd, DSI0_BASE + 0x008));
    printf("DSI_FIFO_STATUS:  0x%08x\n", read_reg(fd, DSI0_BASE + 0x00C));
    printf("DSI_VID_MODE_CTRL:0x%08x\n", read_reg(fd, DSI0_BASE + 0x010));
    printf("DSI_VID_ACTIVE_H: 0x%08x\n", read_reg(fd, DSI0_BASE + 0x024));
    printf("DSI_VID_ACTIVE_V: 0x%08x\n", read_reg(fd, DSI0_BASE + 0x028));
    printf("DSI_VID_TOTAL:    0x%08x\n", read_reg(fd, DSI0_BASE + 0x02C));
    printf("DSI_VID_HSYNC:    0x%08x\n", read_reg(fd, DSI0_BASE + 0x030));
    printf("DSI_VID_VSYNC:    0x%08x\n", read_reg(fd, DSI0_BASE + 0x034));
    printf("DSI_VID_VSYNC_VPOS:0x%08x\n", read_reg(fd, DSI0_BASE + 0x038));
    printf("DSI_CLK_CTRL:     0x%08x\n", read_reg(fd, DSI0_BASE + 0x118));
    printf("DSI_VID_COMP_CTRL:0x%08x\n", read_reg(fd, DSI0_BASE + 0x29c));
    printf("DSI_VID_COMP_CTL2:0x%08x\n", read_reg(fd, DSI0_BASE + 0x2a0));
    printf("DSI_ERR_INT_MASK0:0x%08x\n", read_reg(fd, DSI0_BASE + 0x10C));
    printf("DSI_INT_CTRL:     0x%08x\n", read_reg(fd, DSI0_BASE + 0x110));
    printf("DSI_DLN0_PHY_ERR: 0x%08x\n", read_reg(fd, DSI0_BASE + 0x0B4));

    printf("\n=== DSI-1 Controller (base 0x%x) ===\n", DSI1_BASE);
    printf("DSI_CTRL:         0x%08x\n", read_reg(fd, DSI1_BASE + 0x004));
    printf("DSI_STATUS:       0x%08x\n", read_reg(fd, DSI1_BASE + 0x008));
    printf("DSI_FIFO_STATUS:  0x%08x\n", read_reg(fd, DSI1_BASE + 0x00C));
    printf("DSI_VID_MODE_CTRL:0x%08x\n", read_reg(fd, DSI1_BASE + 0x010));
    printf("DSI_VID_ACTIVE_H: 0x%08x\n", read_reg(fd, DSI1_BASE + 0x024));
    printf("DSI_VID_ACTIVE_V: 0x%08x\n", read_reg(fd, DSI1_BASE + 0x028));
    printf("DSI_VID_TOTAL:    0x%08x\n", read_reg(fd, DSI1_BASE + 0x02C));
    printf("DSI_VID_COMP_CTRL:0x%08x\n", read_reg(fd, DSI1_BASE + 0x29c));
    printf("DSI_CLK_CTRL:     0x%08x\n", read_reg(fd, DSI1_BASE + 0x118));

    close(fd);
    return 0;
}
