# replit.nix - Nix configuration for additional dependencies
{ pkgs }: {
  deps = [
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.ffmpeg
    pkgs.aria2
  ];
}