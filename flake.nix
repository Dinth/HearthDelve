{
  # Hearthdelve on NixOS: `nix run github:Dinth/HearthDelve`
  #
  # Why this shape: the released hearthdelve-linux binary is a PyInstaller
  # onefile with an FHS loader path, which NixOS deliberately lacks (it runs
  # fine under `steam-run` / nix-ld). A fully static build isn't possible for
  # an SDL window app — display/audio libraries must come from the running
  # system. And python-tcod isn't in nixpkgs, while its sdist downloads SDL
  # during the build (hostile to the Nix sandbox).
  #
  # So instead: pin the official manylinux wheel (fixed hash, unpacked purely —
  # its bundled SDL/libtcod resolve via $ORIGIN rpaths), and run the game from
  # source inside a buildFHSEnv that supplies the X11/Wayland/GL/audio client
  # libraries the bundled SDL dlopens at runtime.
  description = "Hearthdelve — a cozy farming roguelike in the terminal";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      wheels = {
        x86_64-linux = {
          url = "https://files.pythonhosted.org/packages/8c/73/74b30e2602b3630e6371a760938e4842e32937ab3c095edf75ac43d2a628/tcod-21.2.1-cp310-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl";
          sha256 = "d8742c9cfd490b53e21acce7773bd02fad9d5e22b224f8d5dad55c0cfc0ad593";
        };
        aarch64-linux = {
          url = "https://files.pythonhosted.org/packages/d7/b7/7f9073a770322f282ec10484323cd3400fe9ca3506f51c70fbb867448a06/tcod-21.2.1-cp310-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl";
          sha256 = "237becb88e131e41feb9856f731dad6ec4e839c5dcf72cf92d1172b4259ef9c1";
        };
      };
      systems = builtins.attrNames wheels;
      forAll = f: nixpkgs.lib.genAttrs systems f;

      mkHearthdelve = system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          pythonEnv = pkgs.python312.withPackages (ps: with ps; [
            numpy cffi attrs typing-extensions
          ]);
          # The official python-tcod wheel, unpacked (cp310-abi3: any Python 3.10+).
          tcodWheel = pkgs.runCommand "python-tcod-21.2.1" { } ''
            mkdir -p $out
            ${pkgs.unzip}/bin/unzip -q ${pkgs.fetchurl wheels.${system}} -d $out
          '';
        in pkgs.buildFHSEnv {
          name = "hearthdelve";
          # Everything the wheel's bundled SDL may dlopen: X11, Wayland, GL, audio.
          targetPkgs = p: with p; [
            xorg.libX11 xorg.libXext xorg.libXcursor xorg.libXrandr
            xorg.libXfixes xorg.libXi xorg.libXrender xorg.libXScrnSaver
            libxkbcommon wayland libGL libdrm
            alsa-lib libpulseaudio udev
          ];
          runScript = pkgs.writeShellScript "hearthdelve-run" ''
            export PYTHONPATH=${tcodWheel}''${PYTHONPATH:+:$PYTHONPATH}
            exec ${pythonEnv}/bin/python ${self}/play.py "$@"
          '';
          meta = {
            description = "Hearthdelve — a cozy farming roguelike in the terminal";
            mainProgram = "hearthdelve";
          };
        };
    in {
      packages = forAll (system: rec {
        hearthdelve = mkHearthdelve system;
        default = hearthdelve;
      });
      apps = forAll (system: rec {
        hearthdelve = {
          type = "app";
          program = "${self.packages.${system}.hearthdelve}/bin/hearthdelve";
        };
        default = hearthdelve;
      });
    };
}
