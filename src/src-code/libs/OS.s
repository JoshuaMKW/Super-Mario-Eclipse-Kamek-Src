    .text
    .file "OS.s"
    .globl DCDisable                    # -- Begin function DCDisable
    .p2align	2
	.type	DCDisable,@function
DCDisable:                              # @DCDisable
.Lfunc_begin0:
    .cfi_startproc
# %bb.0:                                # %entry
    sync
    mfspr 3, HID0
    andi. 3, 3, -0x4000
    mtspr HID0, 3
    blr
.Lfunc_end0:
	.size	DCDisable, .Lfunc_end0-.Lfunc_begin0
	.cfi_endproc
                                        # -- End function
    .text
    .globl ICDisable                    # -- Begin function ICDisable
    .p2align	2
	.type	ICDisable,@function
ICDisable:                              # @ICDisable
.Lfunc_begin1:
    .cfi_startproc
# %bb.0:                                # %entry
    sync
    mfspr 3, HID0
    andi. 3, 3, -0x8000
    mtspr HID0, 3
    blr
.Lfunc_end1:
	.size	ICDisable, .Lfunc_end1-.Lfunc_begin1
	.cfi_endproc
                                        # -- End function
    .ident	"clang version 13.0.0 (https://github.com/DotKuribo/llvm-project.git)"