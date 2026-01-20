import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVideoStackSmall = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M4.78201 6V5C4.78201 3.895 5.67701 3 6.78201 3H17.217C18.322 3 19.217 3.895 19.217 5V6M19 21H5C3.9 21 3 20.1 3 19V8C3 6.895 3.895 6 5 6H19C20.1 6 21 6.9 21 8V19C21 20.105 20.105 21 19 21ZM11.007 10.7421L14.646 12.8941C15.106 13.1661 15.106 13.8321 14.646 14.1041L11.007 16.2561C10.538 16.5331 9.94501 16.1951 9.94501 15.6511V11.3471C9.94601 10.8031 10.539 10.4651 11.007 10.7421Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgVideoStackSmall);
export default Memo;