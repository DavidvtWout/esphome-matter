# If you found this file and don't know what it is, you can safely ignore it.

{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pre-commit-hooks.url = "github:cachix/pre-commit-hooks.nix";
    pre-commit-hooks.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, pre-commit-hooks, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      mkEsphomeOverride =
        owner: rev: hash: extraOverrides:
        pkgs.esphome.overridePythonAttrs (
          old:
          {
            version = rev;
            src = pkgs.fetchFromGitHub {
              inherit owner hash rev;
              repo = "esphome";
            };
            postPatch = ''
              sed -i \
                -e 's/"setuptools==[^"]*"/"setuptools"/' \
                -e 's/"wheel[^"]*"/"wheel"/' \
                pyproject.toml
            '';
            dependencies =
              old.dependencies
              ++ (with pkgs.python3.pkgs; [
                (toPythonModule pkgs.platformio-core)
                filelock
                ninja
                platformdirs
              ]);
            doCheck = false;
          }
          // extraOverrides
        );

      esphome-2026_7_0 =
        mkEsphomeOverride "esphome" "2026.7.0" "sha256-MupDWgc2w913z3POrSIX4YtDqLfCbKqHGAJbzpR8vGc="
          { };
      esphome-2026_7_1 =
        mkEsphomeOverride "esphome" "2026.7.1" "sha256-8D+aqAd4WZQQ29cirNdfHTyffTzEt77cRlUmDutTB5I="
          { };
      esphome-2026_8_1 =
        mkEsphomeOverride "esphome" "2026.8.1" "sha256-zSO7zVBcDiPGOmjMoYDnGYdZSHFRDOzl3iG+I+ybmQM="
          { };
      my-esphome =
        mkEsphomeOverride "DavidvtWout" "openthread-logging"
          "sha256-/sXrTLZidx+pEi0U47dPwReHqZjb/nDviAThLQCo0HY="
          {
            version = "2026.9.0-dev";
            patches = [ ];
          };

      preCommitCheck = pre-commit-hooks.lib.${system}.run {
        src = ./.;
        hooks.clang-format.enable = true;
        hooks.prettier = {
          enable = true;
          files = "\\.(md|yaml)$";
        };
        hooks.nixfmt.enable = true;
        hooks.ruff = {
          enable = true;
          args = [
            "--select"
            "I,F401"
          ]; # Sort imports and remove unused imports
        };
        hooks.ruff-format.enable = true;
      };
    in
    {
      checks.${system}.pre-commit = preCommitCheck;
      formatter.${system} = pkgs.nixfmt;

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          my-esphome
          # esphome  # 2026.6.5 from nixpkgs-unstable
          # esphome-2026_7_0
          # esphome-2026_7_1
          # esphome-2026_8_1
          esptool
        ];
        shellHook = ''
          ${preCommitCheck.shellHook}
          esphome version
        '';
      };
    };
}
