import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStatusOffline = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_3541_21651)"><path d="M11 6C11 8.76142 8.76142 11 6 11C3.23858 11 1 8.76142 1 6C1 3.23858 3.23858 1 6 1C8.76142 1 11 3.23858 11 6Z" stroke="currentColor" strokeWidth={2} /></g><defs><clipPath id="clip0_3541_21651"><rect width={12} height={12} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgStatusOffline);
export default Memo;