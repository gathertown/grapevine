import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCalendar = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M7.50006 3V6M16.5001 3V6M3.00006 9.5H21.0001M5.99881 21H18.0013C19.6575 21 21.0001 19.6574 21.0001 18.0012V7.49875C21.0001 5.84259 19.6575 4.5 18.0013 4.5H5.99881C4.34265 4.5 3.00006 5.84259 3.00006 7.49875V18.0012C3.00006 19.6574 4.34265 21 5.99881 21Z" stroke="currentColor" strokeWidth={1.49938} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCalendar);
export default Memo;