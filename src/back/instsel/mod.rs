//! The instruction selector
//!
//! Note: For now this will be the simplest instruction selector possible.
//!       I'll be able to improve it later, but I need something that works
//!       before I can get there.

// TODO: Finish Instruction Selection
// TODO: Write assembly pretty printer
// TODO: Add tests

use std::collections::HashMap;
use ::Ident;
use back::machine::{Address, Instruction, MachineCode, MachineRegister, NativeInt, REGISTER_COUNT};
use middle::ir;


struct InstructionSelector<'a> {
    ir: &'a ir::Program,
    code: MachineCode,
    globals: HashMap<Ident, usize>,
}

impl<'a> InstructionSelector<'a> {
    fn new(ir: &'a ir::Program) -> InstructionSelector<'a> {
        InstructionSelector {
            ir: ir,
            code: MachineCode::new(),
            globals: HashMap::new(),
        }
    }

    fn init_global(&mut self, name: &Ident, value: NativeInt, offset: usize) {
        let address = offset + REGISTER_COUNT - 1;

        // Store the offset
        self.globals.insert(*name, address);

        // Emit initialization
        self.code.emit(instruction!(MOV [Address::Immediate(address as NativeInt)] value))
    }

    fn trans_fn(&mut self, name: &Ident, body: &[ir::Block], args: &[Ident]) {
        //
    }

    fn translate(mut self) -> MachineCode {
        // First, initialize global variables
        for (offset, symbol) in self.ir.iter().enumerate() {
            if let ir::Symbol::Global { ref name, ref value } = *symbol {
                self.init_global(name, value.val() as NativeInt, offset);
            }
        }

        // Then initialize the stack management registers
        let tos = (REGISTER_COUNT + self.globals.len()) as NativeInt - 1;  // Top of stack
        self.code.emit(instruction!(MOV [Address::MachineRegister(MachineRegister::BP)] tos));
        self.code.emit(instruction!(MOV [Address::MachineRegister(MachineRegister::SP)] tos));

        // Emit a JMP to main
        self.code.emit(instruction!(JMP Ident::new("main")));

        // Translate all functions
        for symbol in self.ir {
            if let ir::Symbol::Function { ref name, ref body, ref args } = *symbol {
                self.trans_fn(name, body, args);
            }
        }

        self.code
    }
}


pub fn select_instructions(ir: &ir::Program) -> MachineCode {
    let is = InstructionSelector::new(ir);
    is.translate()
}