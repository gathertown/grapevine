import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCalendarFilled = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M7.75 2C8.16421 2 8.5 2.33579 8.5 2.75V4H15.5V2.75C15.5 2.33579 15.8358 2 16.25 2C16.6642 2 17 2.33579 17 2.75V4H18.25C19.7688 4 21 5.23122 21 6.75V9H3V6.75C3 5.23122 4.23122 4 5.75 4H7V2.75C7 2.33579 7.33579 2 7.75 2Z" fill="currentColor" /><path d="M3 10.5V18.25C3 19.7688 4.23122 21 5.75 21H18.25C19.7688 21 21 19.7688 21 18.25V10.5H3Z" fill="currentColor" /></svg>;
const Memo = memo(SvgCalendarFilled);
export default Memo;