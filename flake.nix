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

      my-esphome = pkgs.esphome.overridePythonAttrs (old: {
        version = "2026.9.0-dev";
        src = pkgs.fetchFromGitHub {
          owner = "DavidvtWout";
          repo = "esphome";
          rev = "openthread-logging";
          hash = "sha256-562z9kapaLXEIcHK8OwFZwRXF39sGAmeWMSRP22DQ6w=";
        };
        postPatch = ''
          substituteInPlace pyproject.toml \
            --replace-fail "setuptools==84.0.0" "setuptools" \
            --replace-fail "wheel>=0.43,<0.49" "wheel"
        '';
        patches = [ ];
        dependencies =
          old.dependencies
          ++ (with pkgs.python3.pkgs; [
            (toPythonModule pkgs.platformio-core)
            filelock
            platformdirs
          ]);
        doCheck = false;
      });

      preCommitCheck = pre-commit-hooks.lib.${system}.run {
        src = ./.;
        hooks.clang-format.enable = true;
        hooks.nixfmt.enable = true;
        hooks.ruff-format.enable = true;
      };
    in
    {
      checks.${system}.pre-commit = preCommitCheck;
      formatter.${system} = pkgs.nixfmt;

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          my-esphome
          esptool
        ];
        shellHook = preCommitCheck.shellHook;
      };
    };
}
