import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStatusActive = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><g clipPath="url(#clip0_3541_21648)"><path d="M12 6C12 9.31371 9.31371 12 6 12C2.68629 12 0 9.31371 0 6C0 2.68629 2.68629 0 6 0C9.31371 0 12 2.68629 12 6Z" fill="currentColor" /></g><defs><clipPath id="clip0_3541_21648"><rect width={12} height={12} fill="currentColor" /></clipPath></defs></svg>;
const Memo = memo(SvgStatusActive);
export default Memo;