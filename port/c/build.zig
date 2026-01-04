const std = @import("std");

// Helper function to create an executable with specific optimization level
fn createExecutable(
    b: *std.Build,
    target: std.Build.ResolvedTarget,
    optimize: std.builtin.OptimizeMode,
    name_suffix: []const u8,
) *std.Build.Step.Compile {
    const exe_mod = b.createModule(.{
        .target = target,
        .optimize = optimize,
    });

    exe_mod.addIncludePath(b.path("include"));
    exe_mod.addCSourceFiles(.{
        .files = &.{
            "src/khmer_segmenter.c",
            "src/main.c",
            "src/khmer_normalization.c",
            "src/khmer_rule_engine.c",
        },
        .flags = &.{ "-Wall", "-Wextra", "-std=c11", "-D_POSIX_C_SOURCE=200809L" },
    });

    const exe_name = b.fmt("khmer_segmenter{s}", .{name_suffix});
    const exe = b.addExecutable(.{
        .name = exe_name,
        .root_module = exe_mod,
    });

    exe.linkLibC();

    // Link platform-specific libraries
    const target_info = target.result;
    if (target_info.os.tag == .windows) {
        exe.linkSystemLibrary("psapi");
    } else {
        exe.linkSystemLibrary("pthread");
    }

    return exe;
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});

    // Determine platform directory name based on target OS
    const target_info = target.result;
    const platform_dir = switch (target_info.os.tag) {
        .windows => "win",
        .linux => "linux",
        .macos => "macos",
        else => "other",
    };

    // Build both debug and release versions
    const debug_exe = createExecutable(b, target, .Debug, "_debug");
    const release_exe = createExecutable(b, target, .ReleaseFast, "");
    release_exe.root_module.strip = true;

    // Custom install paths for each build type using platform directory
    const debug_path = b.fmt("{s}/bin", .{platform_dir});
    const release_path = b.fmt("{s}/bin", .{platform_dir});

    const debug_install = b.addInstallArtifact(debug_exe, .{
        .dest_dir = .{
            .override = .{
                .custom = debug_path,
            },
        },
    });

    const release_install = b.addInstallArtifact(release_exe, .{
        .dest_dir = .{
            .override = .{
                .custom = release_path,
            },
        },
    });

    // Default install step builds both
    b.getInstallStep().dependOn(&debug_install.step);
    b.getInstallStep().dependOn(&release_install.step);

    // Individual build steps
    const debug_step = b.step("debug", "Build debug version only");
    debug_step.dependOn(&debug_install.step);

    const release_step = b.step("release", "Build release version only");
    release_step.dependOn(&release_install.step);

    // Run commands for each version
    const run_debug_cmd = b.addRunArtifact(debug_exe);
    run_debug_cmd.step.dependOn(&debug_install.step);
    if (b.args) |args| {
        run_debug_cmd.addArgs(args);
    }

    const run_release_cmd = b.addRunArtifact(release_exe);
    run_release_cmd.step.dependOn(&release_install.step);
    if (b.args) |args| {
        run_release_cmd.addArgs(args);
    }

    const run_debug_step = b.step("run-debug", "Run the debug version");
    run_debug_step.dependOn(&run_debug_cmd.step);

    const run_release_step = b.step("run-release", "Run the release version");
    run_release_step.dependOn(&run_release_cmd.step);

    // Default run step uses release version
    const run_step = b.step("run", "Run the release version");
    run_step.dependOn(&run_release_cmd.step);
}
