
$(function(){
	var dtcc_app ={};
	var menuArray = ["weekly","legacy"];
	var reportLinkArray={
			//weekly:["Table 1:Original Report","Table 2:OutStanding Report","Table 3:Correction Report"]
			//weekly:["Table 1:A breakdown of the aggregation type 'Reported Original'  Transactions Summary","Table 2:A breakdown of the aggregation type 'Outstanding Original'  Positions Summary","Table 3:A breakdown of the aggregation type 'Reported Corrected'  Transactions Summary"]
			weekly:["Table 1: A breakdown of the aggregate transactions of current period 'Reported - Original'",
			"Table 2: A breakdown of the aggregate open positions of current period  'Outstanding - Original'",
			"Table 3: A breakdown of the aggregate open positions of current period  'Outstanding - Corrected'",
			"Table 4: A breakdown of the aggregate transactions of current period 'Reported - Corrected'"]
	};
	
	$( "#change_report_date" ).datepicker({
		dateFormat: 'yy-mm-dd',
		changeYear: true,
		maxDate: new Date(),
		beforeShowDay: function(date){
		if(date.getDay() == 5){
            return [true];
        } else {
            return [false];
        }
		}
	});
		
	function reset_panel_main(){
		$("#panel_main_report").hide();
	}
	function getLatestReportDate(){
			var today=new Date();
			var weekday=0;
			var displayDate;
						
			if(today.getDay() == 5){
				displayDate=today;
			}else{
				var startWeekDay=new Date(today.setDate(today.getDate()+weekday - today.getDay()));//day of the start of this week
				startWeekDay.setDate(startWeekDay.getDate()-2);
				displayDate=new Date(startWeekDay);
			}
				var dd=displayDate.getDate();
				var mm=displayDate.getMonth()+1;
				var yyyy=displayDate.getFullYear();
				if(dd<10){
			    	dd='0'+dd;
				} 
				if(mm<10){
			    	mm='0'+mm;
				} 
			var fdisplayDate = yyyy+''+mm+''+dd;
			dtcc_app.availableReportDates.unshift(fdisplayDate);
		}
	function init() {
		$("#panel_main_report").hide();
		dtcc_app.deriv_type = "sft";
		dtcc_app.deriv_type_old = "otc";
		dtcc_app.asset_type = "Weekly_SFTR_Reports";
		dtcc_app.sub_type = "position";
		dtcc_app.report_title = "choose a report";
		dtcc_app.date_selected ="00000000";
		dtcc_app.availableReportDates = ["20181026","20181019","20181012","20181005","20180928","20180921","20180914","20180907","20180831","20180824","20180817","20180810","20180803","20180727","20180720","20180713","20180706","20180629","20180622","20180615","20180608","20180601","20180525","20180518","20180511","20180504","20180427","20180420","20180413","20180406","20180330","20180323","20180316","20180309","20180302","20180223","20180216","20180209","20180202","20180126","20180119","20180112","20180105","20171229","20171222","20171215","20171208","20171201","20171124","20171117","20171110","20171103","20171027","20171020","20171013","20171006","20170929","20170922","20170915","20170908","20170901","20170825","20170818","20170811","20170804","20170728","20170721","20170714","20170707","20170630","20170623","20170616","20170609","20170602","20170526","20170519","20170512","20170505","20170428","20170421","20170414","20170407","20170331","20170324","20170317","20170310","20170303","20170224","20170217","20170210","20170203","20170127","20170120","20170113","20170106","20161230","20161223","20161216","20161209","20161202","20161125","20161118","20161111","20161104","20161028","20161021","20161014","20161007","20160930","20160923","20160916","20160909","20160902","20160826","20160819","20160812","20160805","20160729","20160722","20160715","20160708","20160701","20160624","20160617","20160610","20160603","20160527","20160520","20160513","20160506","20160429","20160422","20160415","20160408","20160401","20160325","20160318","20160311","20160304","20160226","20160219","20160212","20160205","20160129","20160122","20160115","20160108","20160101","20151225","20151218","20151211","20151204","20151127","20151120","20151113","20151106","20151030","20151023","20151016","20151009","20151002","20150925","20150918","20150911","20150904","20150828","20150821","20150814","20150807","20150731","20150724","20150717","20150710","20150703","20150626","20150619","20150612","20150605","20150529","20150522","20150515","20150508","20150501","20150424","20150417","20150410","20150403","20150327","20150320","20150313","20150306","20150227","20150220","20150213","20150206","20150130","20150123","20150116","20150109","20150102","20141226","20141219","20141212","20141205","20141128","20141121","20141114","20141107","20141031","20141024","20141017","20141010","20141003","20140926","20140919","20140912","20140905","20140829","20140822","20140815","20140808","20140801","20140725","20140718","20140711","20140704","20140627","20140620","20140613","20140606","20140530","20140523","20140516","20140509","20140502","20140425","20140418","20140411","20140404","20140328","20140321","20140314","20140307","20140228","20140221","20140214"];
		getLatestReportDate();
		dtcc_app.current_report_date = dtcc_app.availableReportDates[0];
		reset_panel_main();
		//setup_report();
		//show_report();
			}
	function addTablist(){
		$('#accordion_header_sftr_reports').addClass("bold ui-accordion-header ui-helper-reset ui-state-default ui-corner-all ui-accordion-icons")
															  .attr("asset_type","Weekly_STFR_Reports")
															  .append($("<span/>").addClass("ui-accordion-header-icon ui-icon ui-icon-triangle-1-e"));
		
	    $.each(menuArray, function( index, value ) {
	    	var divid;
	    	if(value == "weekly"){
	    		divid="ui-accordian-accordian_sftr_panel-0";
	    		addReportLink(divid,value);
	    	}
	    	$("#"+divid).addClass("ui-accordion-content ui-helper-reset ui-widget-content ui-corner-bottom").css("display","none");
	    });
	}
	function addReportLink(divid,panelid){
		var displayId;
		
		 $.each(reportLinkArray[panelid], function( index, value ) {
			 
			 displayId=value.substring(6, value.indexOf(":"));
	
                
 	 			$("#"+divid).append($("<div/>").addClass("report_link_block")
 	 							  .css("padding","0.2cm")
 	 							  .css("text-align","left")
 	 							  .append($("<span/>").addClass("table_name"))
 	 							  .append($("<span/>").addClass("report_link").attr("report_title",value).attr("display_id",displayId).attr("report_name","table"+displayId).attr("report_download_name","Table "+displayId).html(value))
 	 							  );
 	 			$("#"+divid).append($("<hr/>"));
				
				
 			});
	}
	
	init();
	addTablist();
	$(".accordion").accordion({
		collapsible: true,
		//active: false,
		heightStyle: 'content'
	});
	$("#accordion_otc_and_etd").accordion({
		collapsible: false,
		//active: false,
		heightStyle: 'content'
	});
	$("#accordion_otc,#accordion_etd").accordion({
		collapsible: true,
		active: false,
		heightStyle: 'content'
	});
	$(".ui-accordion-header").click(function(){
                        dtcc_app.asset_type = $(this).attr("asset_type");
                });
	
	$("#accordion_header_weekly_sftr_reports").click(function(){
		                dtcc_app.deriv_type = "sft";
						//$('#change_report_date').val(date2YYYYMMDD(dtcc_app.current_report_date));
						//dtcc_app.display_id = '1';
						//setup_report();
						//getReportWithAjax(dtcc_app.download_org_report_url,"O");
				
						
                });
	$('label[for="btn_otc"]').css("color","#222222");
	$(document).on('click', '.btn_deriv_type', function(){
		
		dtcc_app.deriv_type=$(this).attr("value");
		$('label[for="btn_otc"]').removeClass("ui-state-active");
		$('label[for="btn_etd"]').removeClass("ui-state-active");
		$('label[for="'+$(this).attr("id")+'"]').addClass("ui-state-active");
		if(dtcc_app.deriv_type == "otc")
		{
			$("#accordion_etd" ).hide();
			$('label[for="btn_otc"]').css("color","#222222");
			$('label[for="btn_etd"]').css("color","#212121");
			$("#accordion_etd").accordion("option","active",false);
		}
		else if(dtcc_app.deriv_type == "etd")
		{
			$("#accordion_otc").hide();
			$('label[for="btn_etd"]').css("color","#222222");
			$('label[for="btn_otc"]').css("color","#212121");
			$("#accordion_otc").accordion("option","active",false);
		}
		$("#accordion_" + dtcc_app.deriv_type).show();
	});
	function date2YYYYMMDD(date){
		return date.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3');
	}
	function YYYYMMDD2date(date){
		return date.replace(/-/g,'');
	}
	function setup_report(){
		    
			tmp_asset_type = dtcc_app.asset_type;
			var changedAsset;
			if(dtcc_app.asset_type == "Interest_Rates"){
				changedAsset="Interest_Rate";
			}else{
				changedAsset=dtcc_app.asset_type;
			}
			
			
			
			if(dtcc_app.deriv_type == "sft"){
				dtcc_app.download_org_report_url="/PublicReports/reports/fcasftr/"+"FCAS_TABLE_1_SFT_C_RP_ORG_"+dtcc_app.current_report_date + '.CSV';
				dtcc_app.download_out_report_url="/PublicReports/reports/fcasftr/"+"FCAS_TABLE_2_SFT_C_OUT_ORG_"+dtcc_app.current_report_date + '.CSV';
				dtcc_app.download_out_cor_report_url="/PublicReports/reports/fcasftr/"+"FCAS_TABLE_3_SFT_H_RP_ORG_"+dtcc_app.current_report_date + '.CSV';
				dtcc_app.download_cor_report_url="/PublicReports/reports/fcasftr/"+"FCAS_TABLE_4_SFT_H_RP_CORR_"+dtcc_app.current_report_date + '.CSV';
				
	            
			}
			
			var report_title
			
			var disclaimer = "At the end of the transition period, the first weekly public reported data for the EU SFTR TR (outstanding positions and transactions activity reported to DDRIE) and UK SFTR TR (outstanding positions and transactions activity reported to DDRL) will be published weekly from 12th January 2021. As of this date the method of calculation for the public reports means that it is not possible to simply combine the two datasets to produce an amalgamated total for EU SFTR and UK SFTR reporting. <br><br>For example when the Reporting Counterparty and Branch of the Reporting Counterparty fall under different jurisdiction then the resulting reporting obligations can result in the transaction being legitimately reported to both the EU SFTR and UK SFTR Trade Repositories."

			if (dtcc_app.display_id == '1' || dtcc_app.display_id == '2'){
			report_title = "<h3><b>"+ dtcc_app.report_title + "</b><br><br><small><b>"+ disclaimer +"<b/></small><br><br><b>Report Date (YYYY-MM-DD): " + date2YYYYMMDD(dtcc_app.current_report_date) + "</b></h3>";
			}
		    else{
			report_title = "<h3><b>"+ dtcc_app.report_title + "<br><br>Report Date (YYYY-MM-DD): " + date2YYYYMMDD(dtcc_app.current_report_date) + "</b></h3>";	
			}
           
		   $("#panel_main_report_title").html(report_title);
			
			
				
		}
	 $(document).on('click', '.bothLink', function(){
		 downloadToCSV(makeData("ALL"),"ESMA_Table_"+dtcc_app.display_id+"_"+ "All_Agg"+"_"+dtcc_app.current_report_date + ".CSV");
	 });
	
	 $(document).on( 'click', '.etdListedLink', function (e) {
		 downloadToCSV(makeData("TWO"),"ESMA_Table_"+dtcc_app.display_id+"_"+ "ETD_LISTED"+"_"+dtcc_app.current_report_date + ".CSV");
	 });
	 function show_report(){
         		reset_panel_main();
         		var report_html;
         		var download_link;
				//alert(" I am here in show report :" + dtcc_app.deriv_type + " : display_id :" + dtcc_app.display_id);   
         		if(dtcc_app.asset_type == "Interest_Rates"){
    				changedAsset="Interest_Rate";
    			}else{
    				changedAsset=dtcc_app.asset_type;
    			}
				
				
	            if(dtcc_app.deriv_type == "sft" && dtcc_app.display_id == '1'){
					
	            	report_html = displayCSV();
				    download_link = "<img width=\"17\" hspace=\"3\" height=\"16\" border=\"0\" src=\"/Presentation/Includes/images/icon_4.png\">"+
					"<a style=\" color:#666666 \" href=\"/PublicReports/reports/fcasftr/"+"FCAS_TABLE_1_SFT_C_RP_ORG_"+dtcc_app.current_report_date + ".CSV"+"\">Download Reported Original Report</a>";
			    }
				if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='2'){
		            report_html = displayCSV();
				    download_link = "<img width=\"17\" hspace=\"3\" height=\"16\" border=\"0\" src=\"/Presentation/Includes/images/icon_4.png\">"+
					"<a style=\" color:#666666 \" href=\"/PublicReports/reports/fcasftr/"+"FCAS_TABLE_2_SFT_C_OUT_ORG_"+dtcc_app.current_report_date + ".CSV"+"\">Download OutStanding Original Report</a>";

	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='3'){
		
		            report_html = displayCSV();
				    download_link ="<img width=\"17\" hspace=\"3\" height=\"16\" border=\"0\" src=\"/Presentation/Includes/images/icon_4.png\">"+
					"<a style=\" color:#666666 \" href=\"/PublicReports/reports/fcasftr/"+"FCAS_TABLE_3_SFT_H_RP_ORG_"+dtcc_app.current_report_date +".CSV"+"\">Download OutStanding Corrected Report</a>";

	}
	
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='4'){
		
		            report_html = displayCSV();
				    download_link ="<img width=\"17\" hspace=\"3\" height=\"16\" border=\"0\" src=\"/Presentation/Includes/images/icon_4.png\">"+
					"<a style=\" color:#666666 \" href=\"/PublicReports/reports/fcasftr/"+"FCAS_TABLE_4_SFT_H_RP_CORR_"+dtcc_app.current_report_date +".CSV"+"\">Download Reported Corrected Report</a>";

	}
				
	             $("#panel_main_report_table").html(download_link + report_html);
				 $("#panel_main_report").show();
				 $("tr:odd").css("background-color","#EEEEEE");
	             $('#report_table tr:last').prev().find("tr").addClass("last_row");
	             $('#report_table tr td:first-child').css("background-color", "#CCCCCC");
	             
	            /* if(dtcc_app.display_id == 1){
	            	 $('#report_table tr:eq(8)').css("background-color", "#CCCCCC");
	            	 $('#report_table tr:eq(8) td:first-child').attr("colspan","16").css("text-align","center");
	             }else if(dtcc_app.display_id == 2){
	            	 $('#report_table tr:eq(8)').css("background-color", "#CCCCCC");
	            	 $('#report_table tr:eq(8) td:first-child').attr("colspan","16").css("text-align","center");
	            	 $('#report_table tr:eq(14)').css("background-color", "#CCCCCC");
	            	 $('#report_table tr:eq(14) td:first-child').attr("colspan","16").css("text-align","center");
	             }*/
	   }
	 function makeData(mergeValue){
		 var csv_merged_data;
		 var strDelimiter =  ',';
		 var otc_data=dtcc_app.otc_data.split(/\r?\n|\r/);
			var etd_data=dtcc_app.etd_data.split(/\r?\n|\r/);
			var listed_data=dtcc_app.listed_data.split(/\r?\n|\r/);
		 for(var count = 0; count<otc_data.length; count++)
		    {
			 if(otc_data[count]){
					
					if(count ==0){
						var tableTitle = otc_data[count].split(strDelimiter);
						var tableTitle1 = etd_data[count].split(strDelimiter);
						var tableTitle2 = listed_data[count].split(strDelimiter);
						for(var t_title =0; t_title < tableTitle.length;t_title++) {//OTC
							if(tableTitle[t_title]) {
								if(mergeValue == "ALL")
									csv_merged_data =tableTitle[t_title]+","+tableTitle1[t_title]+","+tableTitle2[t_title]+"\n";
								else
									csv_merged_data =tableTitle1[t_title]+","+tableTitle2[t_title]+"\n";
							}
						}
					}
					if(count == 1){
						var tableHeaders = otc_data[count].split(strDelimiter);
						var tableHeaders1 = etd_data[count].split(strDelimiter);
						var tableHeaders2 = listed_data[count].split(strDelimiter);
						var j;
						if(mergeValue == "ALL"){
							j=1;
						for(var cel_header =0; cel_header < tableHeaders.length;cel_header++) {//OTC 
							csv_merged_data +=tableHeaders[cel_header]+",";
						}
						}else{
							j=0;
						}
						for(var cel_header =j; cel_header < tableHeaders1.length;cel_header++) {//ETD 
							csv_merged_data +=tableHeaders1[cel_header]+",";
						}
						for(var cel_header =1; cel_header < tableHeaders2.length;cel_header++) {//Listed
							csv_merged_data +=tableHeaders2[cel_header]+",";
						}
						csv_merged_data +="\n";
					}
					if(count == 2){
						csv_merged_data +=otc_data[count];
						csv_merged_data +="\n";
					}
					 if(count >2){
						if(otc_data[count] !=null){
							var cell_data = otc_data[count].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g);
							var cell_data1 = etd_data[count].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g);
							var cell_data2 = listed_data[count].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g);
							var k;
							 if(cell_data != null){
								 if(mergeValue == "ALL"){
										k=1;
							     for(var cell_count=0; cell_count<cell_data.length; cell_count++)
							     {	
							    		 csv_merged_data +=cell_data[cell_count]+",";
							     }
								 }else{
									 k=0;
								 }
							     for(var cell_count=k; cell_count<cell_data1.length; cell_count++)
							     {							    	
							    		 csv_merged_data +=cell_data1[cell_count]+",";
							     }
							     for(var cell_count=1; cell_count<cell_data2.length; cell_count++)
							     {							    	
							    		 csv_merged_data +=cell_data2[cell_count]+",";
							     }
							     }
						}
						csv_merged_data +="\n";
			 }
			 }
		    }
		 return csv_merged_data;
	 }
	 function downloadToCSV(csv_data,name){
		 var csvContent=csv_data; 
		 var blob = new Blob([csvContent]);
		 	if (window.navigator.msSaveOrOpenBlob)  
			    window.navigator.msSaveOrOpenBlob(blob, name);
			else
			{
				var a = window.document.createElement("a");
			    a.href = window.URL.createObjectURL(blob, {type: "text/csv"});
			    a.download = name;
			    document.body.appendChild(a);
			    a.click();  
			    document.body.removeChild(a);
			}
	 }
	  function getReportWithAjax(report_url,derivType){

		   $.ajax({
              url: report_url
              ,dataType: 'text'
              ,beforeSend: function() {$('#ajax_wait').show(); }
              ,complete: function() { $('#ajax_wait').hide(); }
              ,cache:false
              ,success: function(data){
                      if(0==data.length){
                              reset_panel_main();
                              var report_html="<h3><font color=\"#222222\"> Report for the chosen date is currently not available.</font></h3>";
                              $("#panel_main_report_table").html(report_html) ;
                              $("#panel_main_report").show();
							  
							  
                         }
                       else{
	                        	if(derivType == "O"){
	                        		dtcc_app.sft_data=data;
	                        		show_report();
	                        	}else if(derivType == "E"){
	                        		dtcc_app.etd_data=data;
	                        		getReportWithAjax(dtcc_app.download_listed_report_url,"L");
	                        	}else if(derivType == "L"){
	                        		dtcc_app.listed_data=data;
	                        		 show_report();
	                        	}else if(derivType == "H"){
	                        		dtcc_app.legacy_data=data;
	                        		 show_report();
	                        	}
                           }
           	}
              ,error: function(){
                      reset_panel_main();
                      var report_html="<h3><font color=\"#222222\"> Report for the chosen date is currently not available.</font></h3>";
                      $("#panel_main_report_table").html(report_html) ;
                      $("#panel_main_report").show();
					 
					  
                  }
		 });
	   }
	   $('#change_report_date').change(function(){
			dtcc_app.current_report_date = YYYYMMDD2date($(this).val());
			dtcc_app.date_selected = dtcc_app.current_report_date;
			reset_panel_main();
			setup_report();
			
			if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='1'){
		getReportWithAjax(dtcc_app.download_org_report_url,"O");
	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='2'){
		getReportWithAjax(dtcc_app.download_out_report_url,"O");
	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='3'){
		getReportWithAjax(dtcc_app.download_out_cor_report_url,"O");
	}
	
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='4'){
		getReportWithAjax(dtcc_app.download_cor_report_url,"O");
	}
			
			
		}); 
		  
	$(document).on('click', '.report_link', function(){
		
		
		dtcc_app.report_name = $(this).attr("report_name");
		dtcc_app.report_title = $(this).attr("report_title");
		dtcc_app.report_download_name=(dtcc_app.report_title.substring((dtcc_app.report_title).indexOf(':')+1)).replace(/:/g," ");
		dtcc_app.display_id = $(this).attr("display_id");
		if(dtcc_app.date_selected == "00000000"){
            dtcc_app.date_selected = dtcc_app.current_report_date;
			dtcc_app.run_selected =  dtcc_app.current_report_date;
    }
    dtcc_app.current_report_date=dtcc_app.date_selected;
    $('#change_report_date').val(date2YYYYMMDD(dtcc_app.date_selected));
	
	reset_panel_main();
	setup_report();
	
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='1'){
		getReportWithAjax(dtcc_app.download_org_report_url,"O");
	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='2'){
		getReportWithAjax(dtcc_app.download_out_report_url,"O");
	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='3'){
		getReportWithAjax(dtcc_app.download_out_cor_report_url,"O");
	}
	if(dtcc_app.deriv_type =="sft" && dtcc_app.display_id =='4'){
		getReportWithAjax(dtcc_app.download_cor_report_url,"O");
	}
	
    }); 
	function displayCSV(){
		var strDelimiter =  ',';
		var otc_data=dtcc_app.sft_data.split(/\r?\n|\r/);
		var root_table='<table id="report_table" class="table table-condensed table-hover table-striped">';
		//alert("data :" + otc_data);
			//alert("count :"+ count + " : data :" + otc_data[count] );
		var count=0;
			
			if(otc_data[count]){
				if(count ==0){
					var tableTitle = otc_data[count].split(strDelimiter);
					
					//root_table+='<thead><tr><th colspan="1" nowrap style=border-collapse:collapse;color:whitesmoke;background-color:#999;>  </th>';
					for(var t_title =0; t_title < tableTitle.length;t_title++) {
						if(tableTitle[t_title]) {
							root_table +='<th colspan="5" nowrap style=border-collapse:collapse;color:whitesmoke;background-color:#999;>'+tableTitle[t_title]+'</th>';
						}
					}
					
					}
					root_table +='</tr></thead>';
				
				
	    
		for(var count1 =1; count1 < otc_data.length;count1++){
			if(otc_data[count1] !=null){
			//var celldata3 = CSVToArray(esma_data[count1],strDelimiter);
			var cell_data = otc_data[count1].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g);
			//console.log("count:" + count1 + " cell data : " + cell_data);
            root_table += '<tr>';
		     if(cell_data != null){//OTC
		         for(var cell_count=0; cell_count<cell_data.length; cell_count++)
		         {
		         root_table += '<td colspan="5" nowrap>'+cell_data[cell_count].replace(/"/g, "")+'</td>';
		         }
			
			  }
		     root_table += '</tr>';
			
		}
	}
			}
		
		root_table += '</tbody>';
		root_table += '</table>';
		
		return root_table;
	}
	function generateHtmlTable(data){
		data=data.replace(/,(?=,)/g, '," "');
		var report_data=data.split(/\r?\n|\r/);
		var table_data = '<table id="report_table" class="table table-condensed table-hover table-striped">';
		for(var count = 0; count<report_data.length; count++)
	    {
			var cell_data = report_data[count].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g);
			
		     table_data += '<tr>';
		     if(cell_data != null){
		     for(var cell_count=0; cell_count<cell_data.length; cell_count++)
		     {
		    	 if(count === 0)
		         {
		          table_data += '<th nowrap colspan="1">'+cell_data[cell_count]+'</th>';
		         }
		         else
		         {
		          table_data += '<td nowrap>'+cell_data[cell_count].replace(/"/g, "")+'</td>';
		         }
		     }
		     }
		     table_data += '</tr>';
	    }
		     table_data += '</table>';
	  return table_data;
	}
});