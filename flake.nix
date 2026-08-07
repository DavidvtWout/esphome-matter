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
      preCommitCheck = pre-commit-hooks.lib.${system}.run {
        src = ./.;
        hooks.clang-format.enable = true;
        hooks.nixfmt.enable = true;
        hooks.ruff-format.enable = true;
      };
    in
    {
      checks.${system}.pre-commit = preCommitCheck;

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [ esphome ];
        shellHook = preCommitCheck.shellHook;
      };
    };
}
