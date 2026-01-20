import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCaretDownSolid = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 8 12" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_382_263173)" transform="translate(0.25, 0)"><path d="M3.21966 8.78203C3.51263 9.075 3.98841 9.075 4.28138 8.78203L7.28138 5.78203C7.49701 5.56641 7.56029 5.24531 7.4431 4.96406C7.32591 4.68281 7.05404 4.5 6.74935 4.5L0.749352 4.50234C0.447008 4.50234 0.172789 4.68516 0.0556016 4.96641C-0.0615859 5.24766 0.00403913 5.56875 0.21732 5.78438L3.21732 8.78438L3.21966 8.78203Z" fill="currentColor" fillOpacity={0.5} /></g><defs><clipPath id="clip0_382_263173"><rect width={7.5} height={12} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgCaretDownSolid);
export default Memo;