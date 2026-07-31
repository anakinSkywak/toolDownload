FFmpeg 64-bit tools - Windows shared build from www.gyan.dev

Version: 2025-01-01-git-d3aa99a4f4

License: LGPL v3

Source Code: https://github.com/FFmpeg/FFmpeg/commit/d3aa99a4f4

Tools:

aviocat
          Use avio to read and write, doing a plain copy of data. It also optionally
          can throttle its operation to a particular speed, to simulate realtime writing.

crypto_bench
          Tool to test the speed of the following algorithms: MD5 SHA-1 SHA-256
          SHA-512 RIPEMD-128 RIPEMD-160 AES-128 CAMELLIA CAST-128 BLOWFISH DES
          TWOFISH RC4 XTEA.

cws2fws
          Convert compressed Macromedia Flash files to uncompressed ones.
          This program is in the public domain.

enum_options
          Enumerate AVOptions and format them in texinfo format.

ffescape
          Escape an input string, adopting the av_get_token() escaping logic.

ffeval
          Simple expression evalutor, using libavutil eval API.

ffhash
          Generate hashes for one or more files, using libavutil hash functions.
          Supported algorithms: MD5 murmur3 RIPEMD128 RIPEMD160 RIPEMD256 RIPEMD320
          SHA160 SHA224 SHA256 SHA512/224 SHA512/256 SHA384 SHA512 CRC32 adler32

fourcc2pixfmt
          Show the relationships between rawvideo pixel formats and FourCC tags.

graph2dot
          Convert a libavfilter graph to a dot file.

ismindex
          Given a .ismv file, this tool creates foo.ism and foo.ismc that is required
          by IIS for serving it.

pktdumper
          Dump AVPackets as they are demuxed by libavformat.

probetest
          Test the format and codec probe functions against random input.

qt-faststart
          Shift moov box in Quicktime and ISOBMFF files (MP4s) to the front.
          This program is in the public domain.

seek_print
          Test the seek implementations of formats.

sidxindex
          Write an MPD file for fragmented MP4 files with a sidx index at
          the start of the fileTest the seek implementations of formats.

venc_data_dump
          This will print per-frame video encoding parameters. Supports H.264/AVC and VP9.

zmqsend
          Send messages to zmq filters.


 '<tool> -h' works for most tools to print help info.
