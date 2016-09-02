from collections import namedtuple
import re

from parsing.parser import *
from .constants import *

class SeqMixin (SourceMixin):

    @property
    def first_token(self):
        return self.seq.first_token

    @property
    def last_token(self):
        return self.seq.last_token


class KCall (SeqMixin, namedtuple("_KCall", "fun args type seq calleeseq")):

    def __init__(self, fun, args, type, seq, calleeseq):
        pass

    def to_code(self):
        return "(" + self.fun.name + " "  + " ".join((arg.to_code() for arg in self.args)) + ")"


class KVal (SeqMixin, namedtuple("Kval", "val type seq")):

    def __init__(self, val, type, seq):
        pass

    def to_code(self):
        return str(self.val)



class SemanticError(CodeError):

    def __init__(self, msg, seq_or_token):
        self.msg = msg
        assert isinstance(seq_or_token, (Seq, Token))
        self.target = seq_or_token

    def __str__(self):
        return self.msg
                    

def _raise(seq_or_token, msg = None):
    msg = msg or "Cannot generate code for"
    msg = msg + ": " + str(seq_or_token)
    raise SemanticError(msg, seq_or_token)


def check_expr(exprstr):
    """ Check a single code expression, returning its associated call tree
        Raises an error if zero or more than one expression is given 
    """
    call_trees = check_code(exprstr)
    assert len(call_trees) == 1
    return call_trees[0]


def check_code(codestr):
    """ Check the code expression, returning the associated call trees
        of all expression found in the code.
    """
    return tuple(kcalls_gen(codestr))


def kcalls_gen(codestr):
    """ Generator to retreive all call trees from codestr. """
    return (check_seq(seq) for seq in seqs_gen(codestr))


def check_seq(seq):
    """ Generate a calltree for the code in seq.
        Returns a KCall.
    """
    return _chk_seq(seq)


def _chk_seq(seq):

    # If a token, check that
    if seq.match(Token):
        return _chk_token(seq)

    # Otherwise we are generating for a sequence    
    assert seq.match(Seq)

    # The sequence must not be empty
    if seq.len == 0:
        _raise(seq, "Non empty sequence expected in place of")

    # if there is just one element in the sequence, 
    # return the value of that element    
    elif seq.len == 1:
        content = seq.items[0]
        # Check if this is a simple token enclosed with parenthesis
        # Such a construct is an error, because it is reserved for the future
        if seq.first_token.match('(') and content.match(Token):
            _raise(content, "Element does not need to be enclosed in parenthesis")
        return _chk_seq(content)

    # Otherwise the seq is a function call with callee first    
    else:
        return _chk_funcall(seq, seq.items[0], seq.items[1:])    


def _chk_funcall(seq, callee, args):

    # At this moment, only builtin llvm operations are permitted    
    if not callee.match(LlvmIdentifier):
        _raise(callee, "Llvm identifier expected for callee")

    # Get requested llvm operation     
    llvm_op = LLVM_OPS.get(callee.llvm_opname)
    if not llvm_op:
        _raise(callee, "Unsupported or undefined LLVM operation")
    expected_types = llvm_op.arg_types    

    # Verify that the correct number of arguments are passed in
    if not len(args) == len(expected_types):
        _raise(callee, 
            "({}) arguments expected but ({}) given for callee".format(len(expected_types), len(args)))    

    # Check the arguments and their types    
    chkedargs = tuple((check_type(_chk_seq(arg), expected_types[i]) for i, arg in enumerate(args)))    

    # Return the function call
    return KCall(llvm_op, chkedargs, llvm_op.ret_type, seq, callee)


def _chk_token(token):
    assert isinstance(token, Token)
    # At the moment, only number exists, 
    if not token.match(Number):
        _raise(token, "Number expected in place of")
    return _chk_number(token)
    

def _chk_number(number):
    assert isinstance(number, Number)
    try:
        # Integer
        if re.match(r"^[0-9]*$", number.text):
            value = int(number.text)
            if -2**(INT_SIZE-1) < value < 2**(INT_SIZE-1):
                return KVal(value, INT, number)
            else:
                _raise(number, "Integer too big to fit in only {} bits".format(INT_SIZE))

        # Floating point    
        return KVal(float(number.text), F64, number)

    except ValueError:
        _raise(number, "Invalid number format")    


def check_type(arg, expected_type):
    # If same type, just return the result
    if arg.type == expected_type:
        return arg

    # If a safe conversion (or promotion) is possible, make it    
    if arg.type == INT and expected_type == F64:
        return KCall(INT_TO_F64_OP, (arg,), F64, arg.seq, arg.seq)
    
    # Otherwise : ERROR        
    _raise(arg.seq, "Type mismatch error, expecting {} but got {} for".format(expected_type, arg.type))

