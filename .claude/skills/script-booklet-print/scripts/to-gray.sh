#!/bin/bash
# Usage: to-gray.sh <in.pdf> <out.pdf>   K-only (DeviceGray) + all text outlined (no font embedding needed at the printer)
set -e
gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dNoOutputFonts -dEmbedAllFonts=true \
   -sColorConversionStrategy=Gray -dProcessColorModel=/DeviceGray -sOutputFile="$2" "$1"
