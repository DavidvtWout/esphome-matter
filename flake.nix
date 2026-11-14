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
            doCheck = false;
          }
          // extraOverrides
        );

      esphome-2026_8_1 =
        mkEsphomeOverride "esphome" "2026.8.1" "sha256-zSO7zVBcDiPGOmjMoYDnGYdZSHFRDOzl3iG+I+ybmQM="
          { };
      esphome-2026_9_1 =
        mkEsphomeOverride "esphome" "2026.9.1" "sha256-/sXrTLZidx+pEi0U47dPwReHqZjb/nDviAThLQCo0HY="
          { };
      esphome-2026_10_0 =
        mkEsphomeOverride "esphome" "2026.10.0" "sha256-0JCrry+AOLY5dmXJWrE5O7uCCDQk5/nKTKI3c+Hf69I="
          { };
      esphome-2026_10_1 =
        mkEsphomeOverride "esphome" "2026.10.1" "sha256-JsPHa3aKHfSSdn31xGSn/+cKynQR8urmegDzCpZTjv0="
          { };
      esphome-2026_10_2 =
        mkEsphomeOverride "esphome" "2026.10.2" "sha256-DMz0dy8mYUglNP036EwVfPr6A0gIoA/YAk80+hhAwfM="
          { };

      my-esphome =
        mkEsphomeOverride "DavidvtWout" "openthread-logging"
          "sha256-/sXrTLZidx+pEi0U47dPwReHqZjb/nDviAThLQCo0HY="
          {
            version = "2026.9.0-dev";
            patches = [ ];
          };

      mkEsphomeCommand =
        version: package:
        pkgs.writeShellScriptBin "esphome-${version}" ''
          exec ${package}/bin/esphome "$@"
        '';

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
            "I"
          ]; # Sort imports
        };
        hooks.ruff-format.enable = true;
      };
    in
    {
      checks.${system}.pre-commit = preCommitCheck;
      formatter.${system} = pkgs.nixfmt;

      # Enter dev shell with `nix develop`
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          my-esphome
          (mkEsphomeCommand "2026.8.1" esphome-2026_8_1)
          (mkEsphomeCommand "2026.9.1" esphome-2026_9_1)
          (mkEsphomeCommand "2026.10.0" esphome-2026_10_0)
          (mkEsphomeCommand "2026.10.1" esphome-2026_10_1)
          (mkEsphomeCommand "2026.10.2" esphome-2026_10_2)
          esptool
        ];
        shellHook = ''
          ${preCommitCheck.shellHook}
          esphome version
        '';
      };
    };
}
