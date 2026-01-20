import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgEventAccepted = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_3541_9310)"><path fillRule="evenodd" clipRule="evenodd" d="M6 12C9.31371 12 12 9.31371 12 6C12 2.68629 9.31371 0 6 0C2.68629 0 0 2.68629 0 6C0 9.31371 2.68629 12 6 12ZM9.86366 4.23866C10.1566 3.94577 10.1566 3.4709 9.86366 3.178C9.57077 2.88511 9.0959 2.88511 8.803 3.178L4.75 7.23101L3.197 5.678C2.9041 5.38511 2.42923 5.38511 2.13634 5.678C1.84344 5.9709 1.84344 6.44577 2.13634 6.73866L4.21967 8.822C4.51256 9.11489 4.98744 9.11489 5.28033 8.822L9.86366 4.23866Z" fill="currentColor" /></g><defs><clipPath id="clip0_3541_9310"><rect width={12} height={12} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgEventAccepted);
export default Memo;