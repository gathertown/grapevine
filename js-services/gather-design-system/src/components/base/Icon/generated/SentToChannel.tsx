import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSentToChannel = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_424_27861)"><path d="M2.91667 2.875L2.25 11.125M5.75 2.875L5.08333 11.125M1.25 4.875H6.75M6.75 9.125H1.25" stroke="currentColor" strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round" /><path d="M8.45833 6.99984H12.5417M8.45833 6.99984L9.91667 5.5415M8.45833 6.99984L9.91667 8.45817" stroke="currentColor" strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round" /></g><defs><clipPath id="clip0_424_27861"><rect width={14} height={14} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgSentToChannel);
export default Memo;