#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import argparse
import os
import sys

EXTGENRE_TAG = "#EXTGENRE:"
EXTIMG_TAG = "#EXTIMG:"


def read_playlist_lines(path):
    with open(path, "r") as f:
        return f.readlines()


def write_playlist_lines(path, lines):
    with open(path, "w") as f:
        f.writelines(lines)


def clean_genre_string(raw_genre):
    if not raw_genre:
        return ""
    return ",".join(g.strip() for g in raw_genre.replace(";", ",").split(",") if g.strip())


def ensure_tags(lines, genre=None, add_img=False, preserve_only=False):
    # Removes old EXTGENRE/EXTIMG tags
    new_lines = [line for line in lines if not (line.startswith(EXTGENRE_TAG) or line.startswith(EXTIMG_TAG))]

    # Preserve existing tags if requested
    genre_line = None
    img_line = None
    for line in lines[:2]:
        if line.startswith(EXTGENRE_TAG):
            genre_line = line.strip()
        if line.startswith(EXTIMG_TAG):
            img_line = line.strip()

    if preserve_only:
        genre = genre_line[len(EXTGENRE_TAG):] if genre_line else ""
        add_img = img_line == EXTIMG_TAG + "local"

    # Builds header lines
    insert = []
    if genre is not None:
        genre_clean = clean_genre_string(genre)
        insert.append(EXTGENRE_TAG + genre_clean + "\n")
    if add_img:
        insert.append(EXTIMG_TAG + "local\n")

    return insert + new_lines


def main():
    parser = argparse.ArgumentParser(description="Ajoute ou conserve les balises EXTGENRE et EXTIMG dans une playlist .m3u")
    parser.add_argument("--file", required=True, help="Chemin de la playlist .m3u")
    parser.add_argument("--set-genre", help="Chaîne de genres (ex: Relax,Instru ou Relax;Instru)")
    parser.add_argument("--add-img", action="store_true", help="Ajoute EXTIMG:local")
    parser.add_argument("--preserve-tags", action="store_true", help="Conserve les balises existantes si elles sont présentes")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Erreur : fichier introuvable {args.file}")
        sys.exit(1)

    try:
        lines = read_playlist_lines(args.file)
        new_lines = ensure_tags(
            lines,
            genre=args.set_genre,
            add_img=args.add_img,
            preserve_only=args.preserve_tags
        )
        write_playlist_lines(args.file, new_lines)
        print("Balises mises à jour avec succès.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
