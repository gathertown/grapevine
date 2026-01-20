import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgHeartBeat = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17.25 12H15.15L13.5 15L10.5 9L8.85001 12H6.75001M12 5.57193C18.3331 -0.86765 29.1898 11.0916 12 20.75C-5.18981 11.0916 5.66688 -0.867651 12 5.57193Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgHeartBeat);
export default Memo;