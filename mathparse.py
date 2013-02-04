# -*- coding: utf-8 -*-
"""Mathematical expression parser.

Source: http://pyparsing.wikispaces.com/file/view/fourFn.py
http://pyparsing.wikispaces.com/message/view/home/15549426

.. note:
    Most of this code comes from the fourFn.py pyparsing example.

    All I've done is rewrap Paul McGuire's fourFn.py as a class,
    so I can use it more easily in other places.

    http://stackoverflow.com/a/2371789/390275

"""

from __future__ import division

import math
import operator
import re

from pyparsing import (CaselessLiteral, Combine, Forward, Group, Literal,
    OneOrMore, Optional, ParseException, StringEnd, Word, ZeroOrMore,
    alphas, alphanums, hexnums, nums, oneOf)

__author__  = 'Paul McGuire'
__version__ = '$Revision:$'
__date__    = '$Date: 2009-03-20 $'


class MathExprParser(object):
    """Parse a simple mathematical expression and allow to evaluate it.

    Supports integers, floats and hexadecimal integers (prefixed with a '$'),
    the constants PI and E and the following operators:

    + - * / %
    **        (power of)
    & | ^     (bitwise and, or and xor)

    The following mathematical functions are supported:

    sin, cos, tan, abs, trunc, round, sgn

    """

    def __init__(self, variables=None, case_sensitive=False):
        """
        expop   :: '**'
        multop  :: '*' | '/'
        addop   :: '+' | '-'
        bitop   :: '&' | '|' | '^'
        integer :: ['+' | '-'] '0'..'9'+
        atom    :: PI | E | real | fn '(' expr ')' | '(' expr ')'
        factor  :: atom [ expop factor ]*
        term    :: factor [ multop factor ]*
        addsub  :: term [ addop term ]*
        expr    :: addsub [ bitop addsub ]*

        """
        self.case_sensitive = case_sensitive

        if variables is None:
            self.variables = {}
        else:
            if not case_sensitive:
                self.variables = dict((k.lower(), v) for k,v in variables.items())
            else:
                self.variables = variables.copy()

        pi    = CaselessLiteral("PI")
        e     = CaselessLiteral("E")
        point = Literal(".")
        plusorminus = Literal('+') | Literal('-')
        number = Word(nums)
        inumber = Combine(Optional(plusorminus) + number)
        #~fnumber = Combine(
            #~Word("+-" + nums, nums) +
            #~Optional(point + Optional(Word(nums))) +
            #~Optional(e + Word("+-" + nums, nums)))
        fnumber = Combine(
            inumber + Optional(point + Optional(number) ) +
            Optional(e + inumber))
        hexnumber = Combine(Literal("$") + OneOrMore(Word(hexnums)))
        ident = Word(alphas + "_", alphanums + "_")
        plus  = Literal("+")
        minus = Literal("-")
        mult  = Literal("*")
        div   = Literal("/")
        modulo = Literal("%")
        and_  = Literal("&")
        or_   = Literal("|")
        xor   = Literal("^")
        lpar  = Literal("(").suppress()
        rpar  = Literal(")").suppress()
        addop  = plus | minus
        multop = mult | div | modulo
        bitop  = and_ | or_ | xor
        expop = Literal("**")

        expr  = Forward()
        atom  = (
            (
                Optional(oneOf("- +")) +
                (pi | e | fnumber | hexnumber | ident |
                    ident + lpar + expr + rpar).setParseAction(self.pushFirst)
            ) | Optional(oneOf("- +")) + Group(lpar + expr + rpar)
        ).setParseAction(self.pushUMinus)

        ###atom = ((pi | e | fnumber | hexnumber | ident
            ###).setParseAction(self.pushFirst) |
            ###(lpar + expr.suppress() + rpar)
        ###)

        # by defining exponentiation as "atom [ ^ factor ]..." instead of
        # "atom [ ^ atom ]...", we get right-to-left exponents,
        # instead of left-to-right, that is, 2^3^2 = 2^(3^2), not (2^3)^2.
        factor = Forward()
        factor << atom + ZeroOrMore((expop + factor).setParseAction(self.pushFirst))
        term = factor + ZeroOrMore((multop + factor).setParseAction(self.pushFirst))
        addop_term = term + ZeroOrMore((addop + term).setParseAction(self.pushFirst))
        bitop_term = addop_term + ZeroOrMore((bitop + addop_term).setParseAction(self.pushFirst))
        expr << bitop_term
        self.bnf = expr + StringEnd()

        # map operator symbols to corresponding arithmetic operations
        epsilon = 1e-12
        self.opn = {
            "+" : operator.add,
            "-" : operator.sub,
            "*" : operator.mul,
            "/" : operator.truediv,
            "%" : operator.mod,
            "**" : operator.pow,
            "&" : operator.and_,
            "|" : operator.or_,
            "^" : operator.xor
        }
        self.fn  = {
            "sin" : math.sin,
            "cos" : math.cos,
            "tan" : math.tan,
            "abs" : abs,
            "trunc" : lambda a: int(a),
            "round" : round,
            "sgn" : lambda a: cmp(a, 0) if abs(a) > epsilon else 0
        }

    def evaluateStack(self, s):
        op = s.pop()
        if op == 'unary -':
            return -self.evaluateStack(s)

        if op in "+-*/%&|^" or op == '**':
            op2 = self.evaluateStack(s)
            op1 = self.evaluateStack(s)
            return self.opn[op](op1, op2)
        elif op == "PI":
            return math.pi # 3.1415926535
        elif op == "E":
            return math.e  # 2.718281828
        elif op in self.fn:
            return self.fn[op](self.evaluateStack(s))
        elif re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', op):
            if not self.case_sensitive:
                op = op.lower()
            return self.variables.get(op, 0)
        elif op.startswith('$'):
            return int(op[1:], 16)
        elif re.match(r'^[+-]?[0-9]+$', op):
            try:
                return long(op)
            except:
                return int(op)
        else:
            return float(op)

    def eval(self, num_string, parseAll=True):
        self.exprStack = []
        results = self.bnf.parseString(num_string, parseAll)
        return self.evaluateStack(self.exprStack[:])

    def pushFirst(self, strg, loc, toks):
        #print(str, loc, toks)
        self.exprStack.append(toks[0])

    def pushUMinus(self, strg, loc, toks):
        if toks and toks[0] == '-':
            self.exprStack.append('unary -')


def _test():
    variables = {
        'a': 12,
        'FOO': 6.0
    }

    expressions = (
        '-15',
        '-1.0',
        '4 + 2',
        '4 - 2',
        '4 * 2',
        '4 / 2',
        '4 % 3',
        '$10 + $FF',
        '160 & $7F',
        '$F ^ $10',
        'a ** 2',
        'foo * 2',
        'sin(PI * 2)'
    )

    mep = MathExprParser(variables)

    for expr in expressions:
        result = mep.eval(expr)
        print("%s = %s" % (expr, result))


if __name__ == '__main__':
    _test()
