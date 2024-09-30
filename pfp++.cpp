//
//  pfp++.cpp
//
//  Copyright 2020 Marco Oliva. All rights reserved.
//

#include <CLI/CLI.hpp>
#include <version.hpp>
#include <utils.hpp>
#include <vcf.hpp>
#include <pfp_algo.hpp>


int main(int argc, char **argv)
{
    CLI::App app("PFP++");
    
    std::vector<std::string> vcfs_file_names;
    std::vector<std::string> refs_file_names;
    std::string fasta_file_path;
    std::string text_file_path;
    std::string out_prefix;
    std::string tmp_dir;
    std::size_t max_samples = 0;
    std::string samples_file_name;
    std::size_t threads = 1;
    bool check = false;
    bool only_trigger_strings = false;
    bool verbose = false;
    std::string haplotype_string = "1";
    
    vcfbwt::pfp::Params params;
    
    app.add_option("-v,--vcf", vcfs_file_names, "List of vcf files. Assuming in genome order!")->allow_extra_args(true)->configurable();
    app.add_option("-r,--ref", refs_file_names, "List of reference files. Assuming in genome order!")->allow_extra_args(true)->configurable();
    app.add_option("-f,--fasta", fasta_file_path, "Fasta file to parse.")->configurable()->check(CLI::ExistingFile);
    app.add_option("-H,--haplotype", haplotype_string, "Haplotype. [1,2,12]")->configurable()->check(CLI::IsMember({"1", "2", "12"}));
    app.add_option("-t,--text", text_file_path, "Text file to parse.")->configurable()->check(CLI::ExistingFile);
    app.add_option("-o,--out-prefix", out_prefix, "Output prefix")->configurable();
    app.add_option("-m, --max", max_samples, "Max number of samples to analyze")->configurable();
    app.add_option("-S, --samples", samples_file_name, "File containing the list of samples to parse")->configurable();
    app.add_option("-w, --window-size", params.w, "Sliding window size")->check(CLI::Range(3, 200))->configurable();
    app.add_option("-p, --modulo", params.p, "Module used during parisng")->check(CLI::Range(5, 20000))->configurable();
    app.add_option("-j, --threads", threads, "Number of threads")->configurable();
    app.add_option("--tmp-dir", tmp_dir, "Tmp file directory")->check(CLI::ExistingDirectory)->configurable();
    app.add_flag("-c, --compression", params.compress_dictionary, "Also output compressed the dictionary")->configurable();
    app.add_flag("-i, --idx", params.report_lengths, "Also output contig length list in .lidx format")->configurable();
    app.add_flag("-l, --leviosam", params.compute_lifting, "Also output lifting file in multiple leviosam format")->configurable();
    app.add_flag("--acgt-only", params.acgt_only, "Convert all non ACGT characters to N.")->configurable();
    app.add_flag("--use-acceleration", params.use_acceleration, "Use reference parse to avoid re-parsing")->configurable();
    app.add_flag("--print-statistics", params.print_out_statistics_csv, "Print out csv containing stats")->configurable();
    app.add_flag("--verbose", verbose, "Verbose output")->configurable();
    app.add_flag_callback("--version",vcfbwt::Version::print,"Version");
    app.set_config("--configure");
    app.allow_windows_style_options();
    
    CLI11_PARSE(app, argc, argv);

    if (verbose) { spdlog::set_level(spdlog::level::debug); }
    
    // Clean file name vectors
    vcfs_file_names.erase(std::remove_if(vcfs_file_names.begin(), vcfs_file_names.end(),
                                         [] (std::string& s) {return s.size() == 0; } ), vcfs_file_names.end());
    refs_file_names.erase(std::remove_if(refs_file_names.begin(), refs_file_names.end(),
                                         [] (std::string& s) {return s.size() == 0; } ), refs_file_names.end());
    
    // Print out configurations
    spdlog::info("Current Configuration:\n{}", app.config_to_str(true,true));
    
    if (not fasta_file_path.empty())
    {
        if (out_prefix.empty()) { out_prefix = fasta_file_path; }
        vcfbwt::pfp::ParserFasta main_parser(params, fasta_file_path, out_prefix);
    
        // Run
        main_parser();
    
        // Close the main parser
        main_parser.close();
    }
    else if (not text_file_path.empty())
    {
        if (out_prefix.empty()) { out_prefix = text_file_path; }
        vcfbwt::pfp::ParserText main_parser(params, text_file_path, out_prefix);
    
        // Run
        main_parser();
    
        // Close the main parser
        main_parser.close();
    }
    else
    {
        // Set tmp file dir
        if (tmp_dir != "") { vcfbwt::TempFile::setDirectory(tmp_dir); }
        
        int last_genotype = 0;
        if ( haplotype_string == "2" or haplotype_string == "12" )
            last_genotype = 1;

        // Set threads accordingly to configuration
        omp_set_num_threads(threads);

        // Parse the VCF
        vcfbwt::VCF vcf(refs_file_names, vcfs_file_names, samples_file_name, params.w, last_genotype, max_samples);
    
        // Create a dictionary common to all references
        vcfbwt::pfp::Dictionary dictionary;

        // Parse all references
        
        std::vector<vcfbwt::pfp::ReferenceParse> references_parse;
        
        auto& references = vcf.get_references();
        auto& references_name = vcf.get_references_name();
        
        references_parse.reserve(references.size());
        // TODO: This might be parallelized as well
        for (size_t i = 0; i < references.size(); ++i) 
            references_parse.push_back( std::move( vcfbwt::pfp::ReferenceParse( references[i], references_name[i], dictionary, params, (i==0) ) ) );

        vcfbwt::pfp::ParserVCF main_parser(params, out_prefix, references_parse, dictionary);
    
        std::vector<vcfbwt::pfp::ParserVCF> workers(threads);
        for (std::size_t i = 0; i < workers.size(); i++)
        {
            std::size_t tag = vcfbwt::pfp::ParserVCF::WORKER | vcfbwt::pfp::ParserVCF::UNCOMPRESSED;
            workers[i].init(params, "", references_parse, dictionary, tag);
            main_parser.register_worker(workers[i]);
        }

        if ( haplotype_string == "1" or haplotype_string == "2")
        {
            if (haplotype_string == "1") { for (std::size_t i = 0; i < workers.size(); i++) { workers[i].set_working_genotype(0); } }
            else { for (std::size_t i = 0; i < workers.size(); i++) { workers[i].set_working_genotype(1); } }
            
            #pragma omp parallel for schedule(static)
            for (std::size_t i = 0; i < vcf.size(); i++)
            {
                int this_thread = omp_get_thread_num();
                spdlog::info("Processing sample [{}/{} H{}]: {}", i, vcf.size(), haplotype_string, vcf[i].id());
                workers[this_thread](vcf[i]);
            }
        }
        else if ( haplotype_string == "12" )
        {
            #pragma omp parallel for schedule(static)
            for (std::size_t i = 0; i < vcf.size(); i++)
            {
                int this_thread = omp_get_thread_num();

                // get first genotype
                workers[this_thread].set_working_genotype(0);
                spdlog::info("Processing sample [{}/{} H{}]: {}", i, vcf.size(), 1, vcf[i].id());
                workers[this_thread](vcf[i]);

                // get second genotype
                workers[this_thread].set_working_genotype(1);
                spdlog::info("Processing sample [{}/{} H{}]: {}", i, vcf.size(), 2, vcf[i].id());
                workers[this_thread](vcf[i]);
            }
        }else{
            spdlog::error("Invalid haplotype: ", haplotype_string, ".\nAllowed haplotypes are 1,2,12.");
            std::exit(EXIT_FAILURE);
        }
        
    
        // close the main parser and exit
        main_parser.close();
    }
}
