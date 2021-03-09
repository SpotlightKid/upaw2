#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Waldorf Microwave II User Programmable Algorithmic Wavetables (UPAW) source
assembler
"""

# standard library imports
import logging
import optparse
import os
import sys
import time

from os.path import abspath, dirname, join

# third-party libraries
#import rtmidi

# mathematical expression parser module
from mathparse import MathExprParser, ParseException


# globals
__program__ = "upaw2.py"
__version__ = "1.0"
__author__  = "Christopher Arndt"
__usage__   = "%s [OPTIONS] FILE.upaw" % __program__

SMF_PREFIX = (
    b'MThd\0\0\0\x06\0\0\0\x01\0\x1e'
    b'MTrk\0\0\x01\x0F\0\xF0\x82\x07'
)

SMF_SUFFIX = b'\x78\xFF\x2F\0'

OPCODELIST = [
    # Mode flags
    "FMFLAG", # FM Synthesis mode ($8000 - $FFFF) on if MSB = 1
    "WSFLAG", # Waveshaping mode ($8000 - $FFFF) on if MSB = 1 and FMFLAG is off
    "EMFLAG", # Envelope mode ($8000 - $FFFF) on if MSB = 1
              # and FMFLAG and WSFLAG are off
              # else Sync/Pulsewidth mode
    "WINDOW", # Apply window function to wave ($8000 - $FFFF) on if MSB = 1
    # FM parameters
    "FCA", # Frequency of carrier A
    "FMA", # Frequency of modulator A
    "MDA", # Modulation depth A
    "FCB", # Frequency of carrier B
    "FMB", # Frequency of modulator B
    "MDB", # Modulation depth B
    # Envelope mode parameters
    "T1", # Time 1
    "L1", # Level 1
    "T2", # etc.
    "L2",
    "T3",
    "L3",
    "T4",
    "L4",
    "T5",
    "L5",
    "T6",
    "L6",
    "T7",
    "L7",
    "T8",
    "L8",
    #  Waveshaping and Sync/Pulswidth mode parameters
    "WA",   # Wavenumber A
    "PA",   # Startphase wave A
    "DA",   # Delta phase wave A
    "NA",   # Number of samples wave A
    "WB",   # Wavenumber B
    "PB",   # Startphase wave B
    "DB",   # Delta phase wave B
    "NB",   # Number of samples wave B
    "WSD",  # Waveshaping depth
    # Parameter increment parameters
    "P1",   # Parameter 1 index
    "I1",   # Parameter 1 increment
    "P2",   # etc.
    "I2",
    "P3",
    "I3",
    "P4",
    "I4",
    "P5",
    "I5",
    "P6",
    "I6",
    "P7",
    "I7",
    "P8",
    "I8",
    "P9",
    "I9",
    "P10",
    "I10",
    "P11",
    "I11",
    "P12",
    "I12",
    "P13",
    "I13",
]

OPCODES = dict(zip(OPCODELIST, range(61)))

log = logging.getLogger(__program__)

class UpawParseError(Exception):
    pass
class UpawUnknownParam(UpawParseError):
    pass
class UpawDuplicateParam(UpawParseError):
    pass


def parse_upaw_file(filename, options):
    upaw_code = dict()
    expr_parser = MathExprParser(OPCODES)

    with open(filename) as fo:
        for line_no, line in enumerate(fo):
            line = line.strip()
            line_no += 1

            if not line or line.startswith(';'):
                continue

            comment_start = line.find(';')
            if comment_start > 0:
                line = line[:comment_start].strip()

            if line.lower().startswith('wavetable'):
                if options.wavetable is None:
                    try:
                        options.wavetable = int(line[9:])
                    except (TypeError, ValueError):
                        raise UpawParseError("Could not parse wavetable number"
                            " at line %i: %r" % (line_no, line[9:]))

                    if 97 > options.wavetable > 128:
                        raise UpawParseError("Wavetable number out of range "
                            " (96-127) at line %i: %i" % (line_no, options.wavetable))

                else:
                    log.debug("Wavetable set via command line option takes precedence.")
            elif line.lower().startswith('device'):
                if options.deviceid is None:
                    try:
                        options.deviceid = int(line[6:])
                    except (TypeError, ValueError):
                        raise UpawParseError("Could not parse deviceid"
                            " at line %i: %r" % (line_no, line[6:]))

                    if 0 > options.deviceid > 127:
                        raise UpawParseError("Device ID out of range (96-127) "
                            "at line %i: %i" % (line_no, options.deviceid))

                else:
                    log.debug("Wavetable set via command line option takes precedence.")
            elif ':' in line:
                param, expr = (v.strip() for v in line.split(':', 1))

                opcode = OPCODES.get(param.upper())

                if opcode is None:
                    raise UpawUnknownParam("Invalid param '%s' at line %i." %
                        (param, line_no))

                if opcode in upaw_code:
                    raise UpawDuplicateParam("Duplicate param '%s' at line %i."
                        % (param, line_no))

                try:
                    upaw_code[opcode] = expr_parser.eval(expr)
                except TypeError as exc:
                    raise UpawParseError("Could not parse expression '%s' "
                        "at line %i: %s" % (expr, line_no, exc))
            else:
                raise UpawParseError("Could not parse '%r' at line %i. "
                    "Expected parameter." % (line, line_no))

    return upaw_code

def _to_nibbles(val):
    c = val >> 12   # upper 4 bits
    c &= 0xF        # for security
    res = [c]
    c = val >> 8;   # next 4 bits
    c &= 0xF;       # mask away superfluous bits
    res.append(c)
    c = val >> 4;   # next 4 bits
    c &= 0xF;       # mask away superfluous bits
    res.append(c)
    c = val         # lower 4 bits
    c &= 0xF;       # mask away superfluous bits
    res.append(c)
    return res

def create_upaw_sysex(upaw_code, options):
    sysex = [
        0xF0,               # Start of sysex
        0x3E,               # Waldorf Electronics Manufacturer ID
        0x0E,               # Microwave II
        options.deviceid & 0x7F,    # clear bit 7 for security
        0x13,               # Control Table Dump
        0x00
    ]

    cs = [options.wavetable - 1]    # checksum starts here
    sysex.append(options.wavetable - 1)

    for val in (0x12DE, 0xC0DE):
        bytes_ = _to_nibbles(val)
        sysex.extend(bytes_)
        cs.extend(bytes_)

    # there seems to be a bug in upaw.c causing it to write the values for
    # 62 instead of 61 parameters to the sysex message, making it 4 bytes
    # longer then necessary. Because of the way the array of values is
    # initialized, the last value will always be -1.
    #
    # For that reason we also use 62 instead of 61 loop iterations here.
    for i in range(62):
        val = upaw_code.get(i, 0 if i < 35 else 0 -(i % 2))

        if isinstance(val, float):
            val = int(val * 512)

        bytes_ = _to_nibbles(val)
        sysex.extend(bytes_)
        cs.extend(bytes_)

    cs = sum(cs)
    cs &= 0x7F;             # checksum to 7 bits */
    sysex.append(cs)
    sysex.append(0xF7)      # End of SysEx or EOX */

    return bytes(sysex)


def write_listfile(filename, upaw_code, options):
    if filename == options.infile:
        raise IOError("Output filename must not be the same as input filename.")

    with open(filename, 'w') as fo:
        fo.write("; UPAW2 Assembler V 1.0 (Python)\n; (c) 2013 Christopher Arndt\n")
        fo.write("; GNU General Public License\n")
        fo.write("; Date : %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        fo.write("; File : \"%s\"\n\n" % options.infile)
        fo.write("Device    $%X\n" % options.deviceid)
        fo.write("Wavetable %i\n\n" % options.wavetable)

        for i in range(61):
            label = OPCODELIST[i]
            val = upaw_code.get(i, 0 if i < 35 else 0 -(i % 2))

            if isinstance(val, float):
                fixp = val
                val = int(val * 512)
            else:
                fixp = float(val / 512.0)

            if i < 35 or i & 0x0001 == 0:
                # if not a parameter index
                fo.write("%-7s: $%04X  ; %5d / % 2.3f\n" %
                        (label,val & 0xFFFF, val, fixp))
            else:
                # if a valid parameter is selected
                if 0 <= val <= 60:
                    fo.write("%-7s: $%04X  ; %5d / %s\n" %
                            (label, val & 0xFFFF, val, OPCODELIST[val]))
                else:
                    fo.write("%-7s: $%04X  ; %5d\n" %
                            (label, val & 0xFFFF, val))


def write_midifile(filename, sysex, options):
    if filename == options.infile:
        raise IOError("Output filename must not be the same as input filename.")

    with open(filename, 'wb') as fo:
        fo.write(SMF_PREFIX)
        fo.write(sysex[1:-1])
        fo.write(SMF_SUFFIX)

def write_sysexfile(filename, sysex, options):
    if filename == options.infile:
        raise IOError("Output filename must not be the same as input filename.")

    with open(filename, 'wb') as fo:
        fo.write(sysex)

def main(args=None):
    optparser = optparse.OptionParser(usage=__usage__, description=__doc__)
    optparser.add_option('-v', '--verbose',
        action="store_true", dest="verbose",
        help="Print debugging info to standard output.")
    optparser.add_option('-d', '--device-id', type="int",
        metavar="ID", dest="deviceid",
        help="Use Sysex DeviceID ID (default: 127).")
    optparser.add_option('-l', '--listfile',
        metavar="FILE", dest="listfile",
        help="Write wavetable program parameter listing to FILE.")
    optparser.add_option('-o', '--output',
        metavar="FILE", dest="outfile",
        help="Write wavetable to MIDI System Exclusive FILE.")
    optparser.add_option('-w', '--wavetable', type="int",
        metavar="NUM", dest="wavetable",
        help="Write wavetable to wavetable slot NUM (default: 32).")
    optparser.add_option('-f', '--smf',
        metavar="FILE", dest="midifile",
        help="Write wavetable to Standard MIDI file FILE.")

    if args is not None:
        opts, args = optparser.parse_args(args)
    else:
        opts, args = optparser.parse_args()

    if opts.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not args:
        sys.stderr.write("No Infile specified!\n")
        optparser.print_help()
        return 2
    else:
        upaw_file = opts.infile = args[0]

    try:
        upaw_code = parse_upaw_file(upaw_file, opts)
    except UpawParseError as exc:
        log.error("Error parsing UPAW input file '%s': %s", upaw_file, exc)
        return 1
    except (OSError, IOError) as exc:
        log.error("Unable to read UPAW input file '%s': %s", upaw_file, exc)
        return 1

    # set defaults AFTER upaw file has been parsed
    if opts.deviceid is None:
        opts.deviceid = 127

    if 0 > opts.deviceid > 127:
        raise ValueError("Invalid Device ID %i.", opts.deviceid)

    if opts.wavetable is None:
        opts.wavetable = 97

    if 97 > opts.wavetable > 128:
        raise ValueError("Invalid Wavetable number %i.", opts.wavetable)

    sysex = create_upaw_sysex(upaw_code, opts)

    if opts.listfile:
        write_listfile(opts.listfile, upaw_code, opts);

    if opts.outfile:
        write_sysexfile(opts.outfile, sysex, opts);

    if opts.midifile:
        write_midifile(opts.midifile, sysex, opts);

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)
