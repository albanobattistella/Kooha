use gtk::glib::{self, translate::ToGlibPtr, FromVariant, StaticVariantType};

use std::borrow::Cow;

#[derive(Debug)]
pub struct Handle(i32);

impl Handle {
    pub fn inner(&self) -> i32 {
        self.0
    }
}

impl StaticVariantType for Handle {
    fn static_variant_type() -> Cow<'static, glib::VariantTy> {
        Cow::Borrowed(glib::VariantTy::HANDLE)
    }
}

impl FromVariant for Handle {
    fn from_variant(value: &glib::Variant) -> Option<Self> {
        unsafe {
            Some(Handle(glib::ffi::g_variant_get_handle(
                value.to_glib_none().0,
            )))
        }
    }
}