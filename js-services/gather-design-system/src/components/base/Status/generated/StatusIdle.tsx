import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStatusIdle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_5214_214)"><path d="M6.59007 0.0300293C9.61732 0.335647 11.9797 2.89291 11.9797 6.00073C11.9795 9.31422 9.29327 12.0007 5.97972 12.0007C2.8722 12.0003 0.315575 9.63719 0.00999451 6.61011C0.728779 7.03928 1.56903 7.28687 2.46703 7.28687C5.11772 7.28666 7.26667 5.13776 7.26683 2.48706C7.26683 1.58905 7.01925 0.748819 6.59007 0.0300293Z" fill="currentColor" /></g><defs><clipPath id="clip0_5214_214"><rect width={12} height={12} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgStatusIdle);
export default Memo;